"""
Valhalla Capital - Background Worker

Owns health checks, pruning, and periodic portfolio snapshots so the
web service stays stateless and can scale independently later.
"""

import asyncio
import logging
import signal
from datetime import timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import SERVICES, DashboardConfig
from .database import Database
from .external_db import ExternalDB
from .health_checker import run_health_checks
from .jobs import run_startup_jobs, snapshot_portfolio

logger = logging.getLogger(__name__)


async def run_worker():
    """Start the background scheduler and wait until shutdown."""
    config = DashboardConfig()
    db = Database(config.db_path)
    ext_db = ExternalDB(config)
    scheduler = AsyncIOScheduler()
    stop_event = asyncio.Event()

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
    )

    await db.connect()
    await ext_db.connect()

    await run_startup_jobs(db, ext_db, config)

    scheduler.add_job(
        run_health_checks,
        "interval",
        seconds=config.poll_interval,
        args=[db],
        id="health_checks",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        db.prune_old_snapshots,
        "cron",
        hour=3,
        minute=0,
        id="prune_snapshots",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        snapshot_portfolio,
        "cron",
        day_of_week="mon-fri",
        hour="13-20",
        minute="*/15",
        timezone=timezone.utc,
        args=[db, ext_db, config],
        id="portfolio_snapshot",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        db.prune_portfolio_snapshots,
        "cron",
        hour=3,
        minute=5,
        id="prune_portfolio_snapshots",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info(
        "Valhalla Capital worker online - polling %d services every %ss",
        len(SERVICES),
        config.poll_interval,
    )

    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        await ext_db.close()
        await db.close()
        logger.info("Valhalla Capital worker shutting down")


def main():
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
