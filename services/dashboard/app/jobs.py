"""
Valhalla Capital - Background Jobs

Async jobs owned by the worker process rather than the web server.
"""

import json
import logging

from .config import SERVICES, DashboardConfig
from .database import Database
from .external_db import ExternalDB
from .fmp import enrich_positions, fetch_quotes
from .health_checker import run_health_checks

logger = logging.getLogger(__name__)


async def snapshot_portfolio(
    db: Database,
    ext_db: ExternalDB,
    config: DashboardConfig,
):
    """Capture a mark-to-market portfolio snapshot."""
    try:
        portfolio = await ext_db.get_portfolio_state()
        if not portfolio or not portfolio.get("positions"):
            return

        tickers = [position["ticker"] for position in portfolio["positions"] if position.get("ticker")]
        if not tickers:
            return

        quotes = await fetch_quotes(config, tickers)
        if not quotes:
            await db.save_portfolio_snapshot(0, 0, error="FMP quotes unavailable")
            logger.warning("Portfolio snapshot skipped: no quotes returned")
            return

        enriched = enrich_positions(portfolio["positions"], quotes)
        market_value = sum(position.get("market_value", 0) for position in enriched)
        total_cost = sum(
            float(position.get("avg_price", 0)) * float(position.get("quantity", 0))
            for position in enriched
        )
        cash_info = await ext_db.get_portfolio_cash()
        cash = cash_info["cash"]
        total_value = market_value + cash

        positions_json = json.dumps(
            [
                {"ticker": position.get("ticker"), "value": position.get("market_value", 0)}
                for position in enriched
            ]
            + [{"ticker": "CASH", "value": round(cash, 2)}]
        )

        await db.save_portfolio_snapshot(total_value, total_cost, positions_json)
        logger.info(
            "Portfolio snapshot: $%s (positions $%s + cash $%s)",
            f"{total_value:,.2f}",
            f"{market_value:,.2f}",
            f"{cash:,.2f}",
        )
    except Exception as error:
        logger.error("Portfolio snapshot failed: %s", error)
        try:
            await db.save_portfolio_snapshot(0, 0, error=str(error))
        except Exception:
            pass


async def prune_and_cleanup_snapshots(db: Database):
    """Remove stale snapshot data on worker startup."""
    active_names = {service.name for service in SERVICES}
    snapshots = await db.get_latest_snapshots()
    stale_names = [name for name in snapshots if name not in active_names]
    if stale_names:
        await db.delete_service_snapshots(stale_names)
        logger.info("Cleaned up snapshots for removed services: %s", stale_names)


async def run_startup_jobs(
    db: Database,
    ext_db: ExternalDB,
    config: DashboardConfig,
):
    """Perform one-time worker startup work."""
    await prune_and_cleanup_snapshots(db)
    await run_health_checks(db)
    await snapshot_portfolio(db, ext_db, config)
