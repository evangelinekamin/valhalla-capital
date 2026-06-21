from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from overseer.config import OverseerSettings
from overseer.core.cycle_runner import run_cycle
from overseer.models.cycle import CYCLE_CONFIGS
from overseer.tools.system_tools import reset_daily_counters, reset_weekly_counters
from overseer.tools.trading import check_pending_trades
from overseer.utils.market_hours import is_market_hours

log = structlog.get_logger()


def _parse_cron(expr: str) -> dict:
    parts = expr.split()
    fields = {}
    names = ["minute", "hour", "day", "month", "day_of_week"]
    for name, value in zip(names, parts):
        if value != "*":
            fields[name] = value
    return fields


class OverseerScheduler:
    def __init__(self, pool, settings: OverseerSettings):
        self._pool = pool
        self._settings = settings
        self._scheduler = AsyncIOScheduler()
        self._running = False

    def setup(self) -> None:
        for cycle_type, config in CYCLE_CONFIGS.items():
            cron_fields = _parse_cron(config.cron_expression)

            self._scheduler.add_job(
                self._run_guarded_cycle,
                CronTrigger(**cron_fields),
                args=[cycle_type],
                id=f"cycle_{cycle_type}",
                name=f"Cycle: {cycle_type}",
                misfire_grace_time=300,
                coalesce=True,
                max_instances=1,
            )
            log.info("cycle_scheduled", cycle_type=cycle_type, cron=config.cron_expression)

        self._scheduler.add_job(
            self._reset_daily,
            CronTrigger(hour=0, minute=0, day_of_week="0-4"),
            id="reset_daily",
            name="Reset daily counters",
        )
        self._scheduler.add_job(
            self._reset_weekly,
            CronTrigger(hour=0, minute=0, day_of_week="0"),
            id="reset_weekly",
            name="Reset weekly counters",
        )
        self._scheduler.add_job(
            self._check_fills,
            CronTrigger(minute="*/10", hour="9-16", day_of_week="0-4"),
            id="check_fills",
            name="Check pending trade fills",
            misfire_grace_time=120,
            coalesce=True,
            max_instances=1,
        )
        log.info("fill_check_scheduled", cron="*/10 9-16 * * 0-4")
        self._scheduler.add_job(
            self._snapshot_daily,
            CronTrigger(hour=16, minute=35, day_of_week="0-4"),
            id="daily_snapshot",
            name="Daily portfolio snapshot for performance tracking",
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        log.info("daily_snapshot_scheduled", cron="35 16 * * 0-4")

    async def _run_guarded_cycle(self, cycle_type: str) -> None:
        config = CYCLE_CONFIGS[cycle_type]

        if config.market_hours_only and not is_market_hours():
            log.debug("cycle_skipped_outside_market", cycle_type=cycle_type)
            return

        from overseer.core.drought import should_skip
        if await should_skip(self._pool, cycle_type):
            log.debug("cycle_skipped_drought_backoff", cycle_type=cycle_type)
            return

        log.info("cycle_triggered", cycle_type=cycle_type)

        try:
            result = await run_cycle(self._pool, self._settings, cycle_type)
            if "error" in result:
                log.error("cycle_failed", cycle_type=cycle_type, error=result["error"])
        except Exception as e:
            log.error("cycle_exception", cycle_type=cycle_type, error=str(e))

    async def _reset_daily(self) -> None:
        await reset_daily_counters(self._pool)

    async def _reset_weekly(self) -> None:
        await reset_weekly_counters(self._pool)

    async def _check_fills(self) -> None:
        log.debug("fill_check_triggered")
        try:
            result = await check_pending_trades(self._pool, self._settings)
            log.info(
                "fill_check_complete",
                checked=result.get("checked", 0),
                updated=len(result.get("updated", [])),
            )
        except Exception as e:
            log.error("fill_check_error", error=str(e))

    async def _snapshot_daily(self) -> None:
        """Capture end-of-day portfolio value for performance tracking."""
        import json as _json
        from datetime import date
        from overseer.memory import working
        from overseer.utils import database as db

        try:
            cached = await working.get(self._pool, "portfolio_state_cached")
            if not cached:
                log.warning("daily_snapshot_skipped", reason="no cached portfolio state")
                return

            # working.get returns whatever is in JSONB — normally a dict, but if
            # the codec round-trips it as a JSON string (asyncpg pool re-init
            # without the JSONB codec re-registered, for example) it will be a
            # str. The old code called .get() on it unconditionally and the
            # AttributeError was swallowed by the outer try — daily snapshots
            # silently stopped running.
            if isinstance(cached, str):
                try:
                    cached = _json.loads(cached)
                except _json.JSONDecodeError:
                    log.error("daily_snapshot_skipped", reason="cached state is a non-JSON string")
                    return
            if not isinstance(cached, dict):
                log.error(
                    "daily_snapshot_skipped",
                    reason=f"cached state has unexpected type: {type(cached).__name__}",
                )
                return

            total_value = cached.get("total_value", 0)
            if total_value <= 0:
                log.warning("daily_snapshot_skipped", reason="zero portfolio value")
                return

            # Compute invested_capital from cash_flows table
            invested = await db.fetchval(
                self._pool,
                "SELECT COALESCE(SUM(amount), 0) FROM cash_flows WHERE flow_date <= $1",
                date.today(),
            )

            await db.execute(
                self._pool,
                """INSERT INTO portfolio_daily (date, total_value, invested_capital)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (date) DO UPDATE
                   SET total_value = $2, invested_capital = $3""",
                date.today(),
                float(total_value),
                float(invested),
            )
            log.info(
                "daily_snapshot_saved",
                date=str(date.today()),
                total_value=total_value,
                invested_capital=float(invested),
            )
        except Exception as e:
            log.error("daily_snapshot_error", error=str(e))

    def start(self) -> None:
        self._scheduler.start()
        self._running = True
        log.info("scheduler_started")

    def stop(self) -> None:
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            log.info("scheduler_stopped")

    @property
    def running(self) -> bool:
        return self._running
