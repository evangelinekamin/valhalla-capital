from __future__ import annotations

from datetime import datetime

import structlog

from overseer.models.cycle import CapabilityWish
from overseer.utils import database as db
from overseer.utils.market_hours import is_market_hours

log = structlog.get_logger()


async def check_circuit_breakers(pool) -> dict:
    daily_pnl = await db.fetchval(
        pool, "SELECT value FROM working_memory WHERE key = 'daily_pnl'"
    )
    portfolio_value = await db.fetchval(
        pool, "SELECT value FROM working_memory WHERE key = 'portfolio_value'"
    )
    daily_trades = await db.fetchval(
        pool, "SELECT count FROM trade_counters WHERE name = 'daily'"
    )
    weekly_trades = await db.fetchval(
        pool, "SELECT count FROM trade_counters WHERE name = 'weekly'"
    )
    circuit_active = await db.fetchval(
        pool, "SELECT value FROM working_memory WHERE key = 'circuit_breaker_active'"
    )

    pnl = float(daily_pnl) if daily_pnl is not None else 0.0
    pv = float(portfolio_value) if portfolio_value is not None else 0.0
    # trade_counters rows are seeded at startup; missing values would mean a
    # truncated table, not a fresh deploy, so default to 0 only as a last resort.
    dt = int(daily_trades) if daily_trades is not None else 0
    wt = int(weekly_trades) if weekly_trades is not None else 0
    cb = bool(circuit_active) if circuit_active is not None else False

    loss_halt_pct = await db.fetchval(
        pool, "SELECT value FROM system_config WHERE key = 'daily_loss_halt_pct'"
    )
    loss_halt = float(loss_halt_pct) if loss_halt_pct is not None else 0.03

    breakers = {
        "daily_loss_halt": pv > 0 and (pnl / pv) <= -loss_halt,
        "max_daily_trades": dt >= 10,
        "max_weekly_trades": wt >= 30,
        "outside_market_hours": not is_market_hours(),
        "circuit_breaker_active": cb,
    }

    any_triggered = any(breakers.values())

    if any_triggered:
        triggered = [k for k, v in breakers.items() if v]
        log.warning("circuit_breakers_triggered", breakers=triggered)

    return {
        "trading_allowed": not any_triggered,
        "breakers": breakers,
        "daily_pnl": pnl,
        "portfolio_value": pv,
        "daily_trades": dt,
        "weekly_trades": wt,
    }


async def request_capability(pool, wish: CapabilityWish) -> int:
    existing = await db.fetchrow(
        pool,
        "SELECT id, frequency FROM capability_wishes WHERE title = $1 AND status = 'open'",
        wish.title,
    )

    if existing:
        await db.execute(
            pool,
            "UPDATE capability_wishes SET frequency = frequency + 1, last_wished_at = NOW() WHERE id = $1",
            existing["id"],
        )
        log.info("capability_wish_incremented", wish_id=existing["id"], title=wish.title)
        return existing["id"]

    wish_id = await db.fetchval(
        pool,
        """INSERT INTO capability_wishes (category, title, description, reasoning, priority)
           VALUES ($1, $2, $3, $4, $5)
           RETURNING id""",
        wish.category,
        wish.title,
        wish.description,
        wish.reasoning,
        wish.priority,
    )
    log.info("capability_wish_created", wish_id=wish_id, title=wish.title)
    return wish_id


async def get_open_wishes(pool, limit: int = 20) -> list[dict]:
    rows = await db.fetch(
        pool,
        """SELECT id, category, title, description, reasoning, priority, frequency,
                  last_wished_at, created_at
           FROM capability_wishes
           WHERE status = 'open'
           ORDER BY frequency DESC, last_wished_at DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def log_decision(pool, cycle_log_id: int | None, decision_type: str,
                       summary: str, reasoning: str, tickers: list[str] | None = None,
                       confidence: float | None = None,
                       falsification_criteria: list | None = None) -> int:
    decision_id = await db.fetchval(
        pool,
        """INSERT INTO decision_journal
           (cycle_log_id, decision_type, summary, reasoning, tickers, confidence, falsification_criteria)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id""",
        cycle_log_id,
        decision_type,
        summary,
        reasoning,
        tickers or [],
        confidence,
        falsification_criteria or [],
    )
    log.info("decision_logged", decision_id=decision_id, decision_type=decision_type)
    return decision_id


async def compare_to_thesis(pool, decision_id: int, current_data: dict) -> dict:
    row = await db.fetchrow(
        pool,
        """SELECT id, summary, reasoning, falsification_criteria, tickers, confidence
           FROM decision_journal WHERE id = $1""",
        decision_id,
    )
    if not row:
        return {"error": f"Decision {decision_id} not found"}

    criteria = row["falsification_criteria"] if row["falsification_criteria"] else []

    result = {
        "decision_id": decision_id,
        "original_summary": row["summary"],
        "original_reasoning": row["reasoning"],
        "falsification_criteria": criteria,
        "tickers": row["tickers"],
        "confidence": row["confidence"],
        "current_data": current_data,
        "instruction": "Review the falsification criteria against current_data. "
                       "Price movement alone does NOT invalidate a thesis. "
                       "Only fundamental changes to the original reasoning justify exit.",
    }

    # Enrich with thesis tracker data if available
    thesis_row = await db.fetchrow(
        pool,
        """SELECT id, thesis_statement, conviction, pillars, catalysts, risks,
                  update_log, target_price, stop_loss, entry_price
           FROM thesis_tracker
           WHERE decision_id = $1 AND status = 'active'""",
        decision_id,
    )
    if thesis_row:
        result["thesis_tracker"] = {
            "thesis_id": thesis_row["id"],
            "thesis_statement": thesis_row["thesis_statement"],
            "conviction": thesis_row["conviction"],
            "pillars": thesis_row["pillars"],
            "catalysts": thesis_row["catalysts"],
            "risks": thesis_row["risks"],
            "update_count": len(thesis_row["update_log"]) if thesis_row["update_log"] else 0,
            "recent_updates": (thesis_row["update_log"] or [])[-3:],
            "target_price": thesis_row["target_price"],
            "stop_loss": thesis_row["stop_loss"],
            "entry_price": thesis_row["entry_price"],
        }

    return result


async def get_trade_count(pool, name: str) -> int:
    """Read a counter from trade_counters. The row is guaranteed to exist
    because bootstrap_schema seeds 'daily' and 'weekly' at startup, so we
    don't need a NULL→0 fallback that masks initialization bugs."""
    return await db.fetchval(
        pool, "SELECT count FROM trade_counters WHERE name = $1", name
    )


async def increment_trade_count(pool) -> None:
    # Single atomic UPDATE on a NOT NULL INTEGER column. Rows are seeded by
    # bootstrap_schema, so RowsAffected==0 here means a real bug (somebody
    # truncated trade_counters), not a counter-uninitialized condition that
    # silently disables the limits.
    await db.execute(
        pool,
        """UPDATE trade_counters
           SET count = count + 1, updated_at = NOW()
           WHERE name IN ('daily', 'weekly')""",
    )


async def reset_daily_counters(pool) -> None:
    await db.execute(
        pool,
        """UPDATE trade_counters
           SET count = 0, period_start = NOW(), updated_at = NOW()
           WHERE name = 'daily'""",
    )
    await db.execute(
        pool,
        """INSERT INTO working_memory (key, value, updated_at)
           VALUES ('daily_pnl', '0'::jsonb, NOW())
           ON CONFLICT (key) DO UPDATE SET value = '0'::jsonb, updated_at = NOW()""",
    )
    log.info("daily_counters_reset")


async def reset_weekly_counters(pool) -> None:
    await db.execute(
        pool,
        """UPDATE trade_counters
           SET count = 0, period_start = NOW(), updated_at = NOW()
           WHERE name = 'weekly'""",
    )
    log.info("weekly_counters_reset")
