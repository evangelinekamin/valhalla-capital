from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import structlog

from overseer.config import OverseerSettings
from overseer.core.agent_loop import run_agent_loop
from overseer.core.context_builder import build_context
from overseer.core.tool_registry import ToolRegistry
from overseer.models.cycle import CYCLE_CONFIGS, CycleConfig
from overseer.tools.portfolio import get_portfolio_state
from overseer.utils import database as db

log = structlog.get_logger()


def _has_new_signal(result: dict) -> bool:
    text = (result.get("final_text") or "").upper()
    drought_phrases = ("SIGNAL DROUGHT", "NO NEW SIGNALS", "ZERO CRITICAL SIGNALS")
    if any(phrase in text for phrase in drought_phrases):
        return False

    tool_calls = result.get("tool_calls", [])
    if not tool_calls:
        return False

    for tc in tool_calls:
        name = tc.get("name", "")
        if name.startswith("query_"):
            preview = str(tc.get("output_preview", ""))
            if '"count": 0' not in preview:
                return True

    return False


MODEL_COST_PER_1K = {
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005, "cache_read": 0.0001, "cache_create": 0.00125},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375},
    "claude-opus-4-6": {"input": 0.015, "output": 0.075, "cache_read": 0.0015, "cache_create": 0.01875},
}


def estimate_cost_cents(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    costs = MODEL_COST_PER_1K.get(model, {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375})
    input_cost = (input_tokens / 1000) * costs["input"]
    output_cost = (output_tokens / 1000) * costs["output"]
    cache_read_cost = (cache_read_tokens / 1000) * costs["cache_read"]
    cache_create_cost = (cache_creation_tokens / 1000) * costs["cache_create"]
    return (input_cost + output_cost + cache_read_cost + cache_create_cost) * 100


async def run_cycle(pool, settings: OverseerSettings, cycle_type: str) -> dict:
    config = CYCLE_CONFIGS.get(cycle_type)
    if not config:
        log.error("unknown_cycle_type", cycle_type=cycle_type)
        return {"error": f"Unknown cycle type: {cycle_type}"}

    cycle_log_id = await db.fetchval(
        pool,
        """INSERT INTO cycle_logs (cycle_type, model)
           VALUES ($1, $2)
           RETURNING id""",
        cycle_type,
        config.model,
    )

    log.info("cycle_start", cycle_type=cycle_type, model=config.model, cycle_log_id=cycle_log_id)

    try:
        try:
            portfolio = await get_portfolio_state(pool, settings)
            log.debug("cycle_portfolio_refresh", total_value=portfolio.total_value)
        except Exception as e:
            log.warning("cycle_portfolio_refresh_failed", error=str(e))

        # Auto-check pending trades at the start of every cycle
        try:
            from overseer.tools.trading import check_pending_trades
            pending_result = await check_pending_trades(pool, settings)
            if pending_result.get("updated"):
                log.info(
                    "cycle_pending_trades_updated",
                    updated=pending_result["updated"],
                    still_pending=pending_result["still_pending"],
                )
        except Exception as e:
            log.warning("cycle_pending_trades_check_failed", error=str(e))

        context = await build_context(pool, cycle_type)
        tool_registry = ToolRegistry(pool, settings)

        max_tokens = 8192
        if cycle_type in ("deep_analysis", "daily_review", "weekly_review", "monthly_review"):
            max_tokens = 16384

        result = await run_agent_loop(
            settings=settings,
            tool_registry=tool_registry,
            system_prompt=context["system"],
            user_message=context["user_message"],
            model=config.model,
            max_tokens=max_tokens,
            cycle_log_id=cycle_log_id,
        )

        cost_cents = estimate_cost_cents(
            config.model,
            result["tokens"]["input"],
            result["tokens"]["output"],
            cache_read_tokens=result["tokens"].get("cache_read", 0),
            cache_creation_tokens=result["tokens"].get("cache_creation", 0),
        )

        if cost_cents > config.max_cost_cents:
            log.warning(
                "cycle_cost_exceeded",
                cycle_type=cycle_type,
                cost_cents=cost_cents,
                max_cents=config.max_cost_cents,
            )

        await db.execute(
            pool,
            """UPDATE cycle_logs
               SET completed_at = NOW(),
                   tokens_used = $1,
                   tools_called = $2,
                   cost_cents = $3,
                   summary = $4
               WHERE id = $5""",
            result["tokens"],
            [tc["name"] for tc in result["tool_calls"]],
            cost_cents,
            result["final_text"][:2000],
            cycle_log_id,
        )

        # UPSERT with tz-aware ISO timestamp. A bare UPDATE silently no-ops on
        # missing rows (first-run, DB reset), leaving the LLM with a stale or
        # absent last_cycle_at; a tz-naive `utcnow()` would also break
        # subtraction against tz-aware timestamps elsewhere.
        await db.execute(
            pool,
            """INSERT INTO working_memory (key, value, updated_at)
               VALUES ('last_cycle_at', to_jsonb($1::text), NOW())
               ON CONFLICT (key) DO UPDATE
                 SET value = to_jsonb($1::text), updated_at = NOW()""",
            datetime.now(timezone.utc).isoformat(),
        )

        # Drought tracking
        try:
            from overseer.core.drought import record_actual_run, update_drought
            had_signal = _has_new_signal(result)
            await record_actual_run(pool, cycle_type)
            await update_drought(pool, cycle_type, had_signal)
        except Exception as e:
            log.warning("drought_tracking_failed", cycle_type=cycle_type, error=str(e))

        log.info(
            "cycle_complete",
            cycle_type=cycle_type,
            cost_cents=round(cost_cents, 2),
            iterations=result["iterations"],
            tool_calls=len(result["tool_calls"]),
        )

        return {
            "cycle_type": cycle_type,
            "cycle_log_id": cycle_log_id,
            "cost_cents": round(cost_cents, 2),
            "iterations": result["iterations"],
            "tool_calls": len(result["tool_calls"]),
            "summary": result["final_text"][:500],
        }

    except Exception as e:
        log.error("cycle_error", cycle_type=cycle_type, error=str(e))
        await db.execute(
            pool,
            "UPDATE cycle_logs SET completed_at = NOW(), error = $1 WHERE id = $2",
            str(e)[:2000],
            cycle_log_id,
        )
        return {
            "cycle_type": cycle_type,
            "cycle_log_id": cycle_log_id,
            "error": str(e),
        }
