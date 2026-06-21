from __future__ import annotations

from datetime import datetime, timezone

import asyncpg
import structlog

from overseer.memory import working

log = structlog.get_logger()

# Effective intervals in minutes per drought level.
# Level 0 = base interval (no drought), each subsequent level backs off further.
BACKOFF_INTERVALS: dict[str, list[int]] = {
    "quick_check": [30, 60, 120, 120],
    "data_synthesis": [240, 480],
}


async def _read_level(pool: asyncpg.Pool, level_key: str) -> int:
    """Read the drought level as an int, self-healing corrupted values.

    The key shares the working_memory namespace with LLM-writable keys and
    was being clobbered by write_reflection calls with narrative strings.
    Any non-integer value is treated as level 0 and rewritten so subsequent
    scheduler ticks don't log-spam.
    """
    raw = await working.get(pool, level_key)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        log.warning(
            "drought_level_corrupted_resetting",
            level_key=level_key,
            raw_type=type(raw).__name__,
        )
        await working.set(pool, level_key, "0")
        return 0


async def should_skip(pool: asyncpg.Pool, cycle_type: str) -> bool:
    intervals = BACKOFF_INTERVALS.get(cycle_type)
    if intervals is None:
        return False

    level_key = f"{cycle_type}_drought_level"
    last_run_key = f"{cycle_type}_last_actual_run_at"

    try:
        drought_level = await _read_level(pool, level_key)
        if drought_level == 0:
            return False

        last_run_raw = await working.get(pool, last_run_key)
        if not last_run_raw or last_run_raw == "null":
            return False

        last_run = datetime.fromisoformat(str(last_run_raw))
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        elapsed_minutes = (now - last_run).total_seconds() / 60

        capped_level = min(drought_level, len(intervals) - 1)
        required_interval = intervals[capped_level]

        if elapsed_minutes < required_interval:
            log.debug(
                "drought_skip",
                cycle_type=cycle_type,
                drought_level=drought_level,
                elapsed_min=round(elapsed_minutes, 1),
                required_min=required_interval,
            )
            return True

        return False

    except Exception as e:
        log.warning("drought_should_skip_error", cycle_type=cycle_type, error=str(e))
        return False


async def record_actual_run(pool: asyncpg.Pool, cycle_type: str) -> None:
    if cycle_type not in BACKOFF_INTERVALS:
        return

    key = f"{cycle_type}_last_actual_run_at"
    now = datetime.now(timezone.utc).isoformat()
    try:
        await working.set(pool, key, now)
    except Exception as e:
        log.warning("drought_record_run_error", cycle_type=cycle_type, error=str(e))


async def update_drought(pool: asyncpg.Pool, cycle_type: str, had_signal: bool) -> None:
    intervals = BACKOFF_INTERVALS.get(cycle_type)
    if intervals is None:
        return

    level_key = f"{cycle_type}_drought_level"
    max_level = len(intervals) - 1

    try:
        current_level = await _read_level(pool, level_key)

        if had_signal:
            new_level = 0
        else:
            new_level = min(current_level + 1, max_level)

        if new_level != current_level:
            await working.set(pool, level_key, str(new_level))
            log.info(
                "drought_level_changed",
                cycle_type=cycle_type,
                old_level=current_level,
                new_level=new_level,
                had_signal=had_signal,
            )
        else:
            log.debug(
                "drought_level_unchanged",
                cycle_type=cycle_type,
                level=current_level,
                had_signal=had_signal,
            )

    except Exception as e:
        log.warning("drought_update_error", cycle_type=cycle_type, error=str(e))
