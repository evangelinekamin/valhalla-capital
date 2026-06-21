from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def is_market_hours(now: datetime | None = None) -> bool:
    et = (now or datetime.now(ET)).astimezone(ET)
    if et.weekday() >= 5:
        return False
    market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= et < market_close


def is_weekday(now: datetime | None = None) -> bool:
    et = (now or datetime.now(ET)).astimezone(ET)
    return et.weekday() < 5


def next_market_open(now: datetime | None = None) -> datetime:
    et = (now or datetime.now(ET)).astimezone(ET)
    candidate = et.replace(hour=9, minute=30, second=0, microsecond=0)
    # Use strict `>` so when called at exactly 09:30:00 ET we return today's
    # open, not tomorrow's — the prior `>=` check advanced a full day at the
    # instant of market open, pushing the next scheduler wake-up 24h out.
    if et > candidate:
        from datetime import timedelta
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        from datetime import timedelta
        candidate += timedelta(days=1)
    return candidate
