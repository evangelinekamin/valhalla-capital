"""Time and market hours utilities."""
from datetime import datetime, time as dt_time
from typing import Tuple

import pytz

# US Eastern timezone (NYSE/NASDAQ)
ET = pytz.timezone("US/Eastern")

# Market hours (regular trading)
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)


def is_market_open(now: datetime | None = None) -> Tuple[bool, str]:
    """
    Check if US stock market is currently open.

    Args:
        now: Optional datetime to check (defaults to current time)

    Returns:
        Tuple of (is_open: bool, message: str)
    """
    if now is None:
        now = datetime.now(ET)
    else:
        # Convert to Eastern time if not already
        if now.tzinfo is None:
            now = ET.localize(now)
        else:
            now = now.astimezone(ET)

    # Weekend check
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False, "Market closed (weekend)"

    # Market hours check
    current_time = now.time()
    if not (MARKET_OPEN <= current_time <= MARKET_CLOSE):
        return (
            False,
            f"Outside market hours ({current_time.strftime('%H:%M')} ET, "
            f"market: {MARKET_OPEN.strftime('%H:%M')}-{MARKET_CLOSE.strftime('%H:%M')})",
        )

    return True, "Market is open"


def get_current_et_time() -> datetime:
    """Get current time in US Eastern timezone."""
    return datetime.now(ET)


def is_trading_day(date: datetime) -> bool:
    """
    Check if given date is a trading day (weekday).

    Note: This does NOT account for market holidays.

    Args:
        date: Date to check

    Returns:
        True if weekday, False if weekend
    """
    return date.weekday() < 5
