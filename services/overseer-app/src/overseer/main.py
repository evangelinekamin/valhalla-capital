from __future__ import annotations

import asyncio
import signal
import sys

import structlog

from overseer.config import get_settings
from overseer.core.scheduler import OverseerScheduler
from overseer.utils.database import bootstrap_schema, close_pool, get_pool
from overseer.utils.logging import setup_logging

log = structlog.get_logger()


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    log.info(
        "overseer_starting",
        trading_mode=settings.trading_mode,
        db=settings.db_name,
    )

    pool = await get_pool(settings)
    await bootstrap_schema(pool)

    log.info("database_connected")

    scheduler = OverseerScheduler(pool, settings)
    scheduler.setup()
    scheduler.start()

    discord_task = None
    try:
        from overseer.tools.discord_tools import get_notifier
        notifier = await get_notifier(settings)
        await notifier.send_message("Valkyrie Overseer online. All systems nominal.")
        log.info("discord_connected")
    except Exception as e:
        log.warning("discord_connect_failed", error=str(e))

    shutdown_event = asyncio.Event()

    def _signal_handler(sig, frame):
        log.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    log.info("overseer_running", message="Waiting for scheduled cycles...")

    try:
        await shutdown_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass

    log.info("overseer_shutting_down")

    scheduler.stop()

    try:
        from overseer.tools.discord_tools import send_discord_message
        await send_discord_message(settings, "Valkyrie Overseer shutting down.")
    except Exception:
        pass

    try:
        from overseer.tools.discord_tools import _notifier
        if _notifier:
            await _notifier.stop()
    except Exception:
        pass

    await close_pool()
    log.info("overseer_stopped")


async def run_single_cycle(cycle_type: str) -> dict:
    settings = get_settings()
    setup_logging(settings.log_level)

    pool = await get_pool(settings)

    from overseer.core.cycle_runner import run_cycle
    result = await run_cycle(pool, settings, cycle_type)

    await close_pool()
    return result


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "cycle":
        if len(sys.argv) < 3:
            print("Usage: python -m overseer.main cycle <cycle_type>")
            print("Types: quick_check, data_synthesis, deep_analysis, daily_review, weekly_review, monthly_review")
            sys.exit(1)
        cycle_type = sys.argv[2]
        result = asyncio.run(run_single_cycle(cycle_type))
        import json
        print(json.dumps(result, indent=2, default=str))
    else:
        asyncio.run(main())


if __name__ == "__main__":
    cli()
