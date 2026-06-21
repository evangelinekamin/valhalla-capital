"""Spending reporting tool using Anthropic Admin API + internal cycle_logs."""
from __future__ import annotations

import structlog

from overseer.config import OverseerSettings
from overseer.utils import database as db
from overseer.utils.admin_api import get_spending_summary

log = structlog.get_logger()


async def _get_today_from_cycle_logs(pool) -> dict:
    """Get today's spending estimate from internal cycle_logs table."""
    rows = await db.fetch(
        pool,
        """SELECT model, cost_cents
           FROM cycle_logs
           WHERE started_at >= CURRENT_DATE
             AND completed_at IS NOT NULL
             AND cost_cents IS NOT NULL""",
    )
    by_model: dict[str, float] = {}
    total_cents = 0.0
    for row in rows:
        model = row["model"]
        cents = float(row["cost_cents"])
        total_cents += cents
        by_model[model] = by_model.get(model, 0.0) + cents

    return {
        "today_estimated_usd": round(total_cents / 100, 4),
        "today_by_model": {
            model: {"estimated_cost_usd": round(cents / 100, 4)}
            for model, cents in sorted(by_model.items(), key=lambda x: -x[1])
        },
        "source": "internal_cycle_logs",
    }


async def check_spending(pool, settings: OverseerSettings, days: int = 1) -> dict:
    """
    Get spending data combining Admin API (historical) and cycle_logs (today).

    Args:
        pool: Database connection pool
        settings: Overseer settings (contains admin API key)
        days: Number of days to report (1 = today, 7 = past week, 30 = past month)

    Returns:
        Spending summary with costs by model
    """
    result = {}

    # Always include today's data from cycle_logs (Admin API doesn't have real-time today data)
    today_data = await _get_today_from_cycle_logs(pool)
    result["today"] = today_data

    # For multi-day queries, also fetch from Admin API
    if days > 1 and settings.anthropic_admin_api_key:
        api_data = await get_spending_summary(settings.anthropic_admin_api_key, days=days)
        result["period"] = api_data
    elif days == 1:
        result["note"] = (
            "Showing today's Valkyrie spending from internal logs. "
            "Admin API cost data is only available for completed days (yesterday and earlier). "
            "Use days=7 or days=30 for historical Anthropic billing data."
        )

    if not settings.anthropic_admin_api_key and days > 1:
        result["warning"] = "ANTHROPIC_ADMIN_API_KEY not configured - only showing internal cycle_logs data"

    return result
