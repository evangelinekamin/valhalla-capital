"""Thesis tracker tools for structured position thesis management."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import asyncpg
import structlog

from overseer.utils import database as db

log = structlog.get_logger()


async def get_active_theses(pool: asyncpg.Pool, ticker: str | None = None) -> dict:
    """Get all active theses, optionally filtered by ticker."""
    if ticker:
        rows = await db.fetch(
            pool,
            """SELECT id, decision_id, ticker, position_type, thesis_statement,
                      conviction, pillars, catalysts, risks, update_log,
                      target_price, stop_loss, valuation_methodology,
                      entry_price, entry_date, created_at, updated_at
               FROM thesis_tracker
               WHERE status = 'active' AND ticker = $1
               ORDER BY created_at DESC""",
            ticker.upper(),
        )
    else:
        rows = await db.fetch(
            pool,
            """SELECT id, decision_id, ticker, position_type, thesis_statement,
                      conviction, pillars, catalysts, risks, update_log,
                      target_price, stop_loss, valuation_methodology,
                      entry_price, entry_date, created_at, updated_at
               FROM thesis_tracker
               WHERE status = 'active'
               ORDER BY created_at DESC""",
        )

    theses = []
    for row in rows:
        thesis = dict(row)
        thesis["created_at"] = thesis["created_at"].isoformat() if thesis["created_at"] else None
        thesis["updated_at"] = thesis["updated_at"].isoformat() if thesis["updated_at"] else None
        thesis["entry_date"] = thesis["entry_date"].isoformat() if thesis["entry_date"] else None
        theses.append(thesis)

    return {"theses": theses, "count": len(theses)}


async def create_thesis(
    pool: asyncpg.Pool,
    ticker: str,
    thesis_statement: str,
    decision_id: int | None = None,
    position_type: str = "LONG",
    conviction: str = "MEDIUM",
    pillars: list[dict] | None = None,
    catalysts: list[dict] | None = None,
    risks: list[dict] | None = None,
    target_price: float | None = None,
    stop_loss: float | None = None,
    valuation_methodology: str | None = None,
    entry_price: float | None = None,
) -> dict:
    """Create a new thesis for a position."""
    ticker_upper = ticker.upper()

    # Check for existing active thesis
    existing = await db.fetchval(
        pool,
        "SELECT id FROM thesis_tracker WHERE ticker = $1 AND status = 'active'",
        ticker_upper,
    )
    if existing:
        return {
            "status": "already_exists",
            "thesis_id": existing,
            "message": f"Active thesis already exists for {ticker_upper} (id={existing}). Use update_thesis to modify it.",
        }

    thesis_id = await db.fetchval(
        pool,
        """INSERT INTO thesis_tracker (
               decision_id, ticker, position_type, thesis_statement,
               conviction, pillars, catalysts, risks,
               target_price, stop_loss, valuation_methodology,
               entry_price, entry_date
           ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
           RETURNING id""",
        decision_id,
        ticker_upper,
        position_type.upper(),
        thesis_statement,
        conviction.upper(),
        json.dumps(pillars or []),
        json.dumps(catalysts or []),
        json.dumps(risks or []),
        target_price,
        stop_loss,
        valuation_methodology,
        entry_price,
        date.today() if entry_price else None,
    )

    log.info("thesis_created", thesis_id=thesis_id, ticker=ticker_upper)
    return {"status": "created", "thesis_id": thesis_id, "ticker": ticker_upper}


async def update_thesis(
    pool: asyncpg.Pool,
    thesis_id: int,
    data_point: str,
    thesis_impact: str,
    action: str = "MAINTAIN",
    conviction_change: str | None = None,
    pillar_updates: list[dict] | None = None,
    new_catalysts: list[dict] | None = None,
    new_risks: list[dict] | None = None,
    target_price: float | None = None,
    stop_loss: float | None = None,
) -> dict:
    """Update a thesis with new information and log the update."""
    row = await db.fetchrow(
        pool,
        """SELECT id, ticker, conviction, pillars, catalysts, risks, update_log
           FROM thesis_tracker WHERE id = $1 AND status = 'active'""",
        thesis_id,
    )
    if not row:
        return {"error": f"Active thesis {thesis_id} not found"}

    # Build update log entry
    log_entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "data_point": data_point,
        "thesis_impact": thesis_impact,
        "action": action,
        "conviction_change": conviction_change,
    }

    update_log = row["update_log"] if isinstance(row["update_log"], list) else json.loads(row["update_log"] or "[]")
    update_log.append(log_entry)

    # Update pillars if provided
    pillars = row["pillars"] if isinstance(row["pillars"], list) else json.loads(row["pillars"] or "[]")
    if pillar_updates:
        pillar_map = {p.get("id"): p for p in pillars}
        new_pillars: list[dict] = []
        for update in pillar_updates:
            pid = update.get("id")
            if pid and pid in pillar_map:
                pillar_map[pid]["current_status"] = update.get("current_status", pillar_map[pid].get("current_status"))
                pillar_map[pid]["trend"] = update.get("trend", pillar_map[pid].get("trend"))
                pillar_map[pid]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            else:
                update["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                new_pillars.append(update)
        # Rebuild: existing (possibly updated) pillars + newly-added ones.
        # Prior version appended to `pillars` inside the loop and then
        # reassigned `pillars = list(pillar_map.values())` which dropped the
        # appended new pillars on the floor.
        pillars = list(pillar_map.values()) + new_pillars

    # Append new catalysts
    catalysts = row["catalysts"] if isinstance(row["catalysts"], list) else json.loads(row["catalysts"] or "[]")
    if new_catalysts:
        catalysts.extend(new_catalysts)

    # Append new risks
    risks = row["risks"] if isinstance(row["risks"], list) else json.loads(row["risks"] or "[]")
    if new_risks:
        risks.extend(new_risks)

    # Determine new conviction
    new_conviction = conviction_change if conviction_change else row["conviction"]

    # Build UPDATE
    await db.execute(
        pool,
        """UPDATE thesis_tracker
           SET conviction = $1,
               pillars = $2,
               catalysts = $3,
               risks = $4,
               update_log = $5,
               target_price = COALESCE($6, target_price),
               stop_loss = COALESCE($7, stop_loss),
               updated_at = NOW()
           WHERE id = $8""",
        new_conviction,
        json.dumps(pillars),
        json.dumps(catalysts),
        json.dumps(risks),
        json.dumps(update_log),
        target_price,
        stop_loss,
        thesis_id,
    )

    log.info(
        "thesis_updated",
        thesis_id=thesis_id,
        ticker=row["ticker"],
        action=action,
        conviction=new_conviction,
    )

    return {
        "status": "updated",
        "thesis_id": thesis_id,
        "ticker": row["ticker"],
        "conviction": new_conviction,
        "updates_count": len(update_log),
    }


async def close_thesis(
    pool: asyncpg.Pool,
    thesis_id: int,
    reason: str,
    outcome: str = "exited",
) -> dict:
    """Close a thesis (exited, invalidated, or confirmed)."""
    row = await db.fetchrow(
        pool,
        "SELECT id, ticker, decision_id FROM thesis_tracker WHERE id = $1 AND status = 'active'",
        thesis_id,
    )
    if not row:
        return {"error": f"Active thesis {thesis_id} not found"}

    await db.execute(
        pool,
        """UPDATE thesis_tracker
           SET status = $1, close_reason = $2, closed_at = NOW(), updated_at = NOW()
           WHERE id = $3""",
        outcome,
        reason,
        thesis_id,
    )

    # Also update the linked decision_journal entry if it exists
    if row["decision_id"]:
        await db.execute(
            pool,
            """UPDATE decision_journal
               SET outcome = $1, outcome_details = $2, reviewed_at = NOW()
               WHERE id = $3""",
            outcome,
            json.dumps({"close_reason": reason}),
            row["decision_id"],
        )

    log.info("thesis_closed", thesis_id=thesis_id, ticker=row["ticker"], outcome=outcome)

    return {
        "status": "closed",
        "thesis_id": thesis_id,
        "ticker": row["ticker"],
        "outcome": outcome,
    }
