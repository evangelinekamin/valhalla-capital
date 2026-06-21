"""Unit tests for time utilities."""
import pytest
from datetime import datetime, time as dt_time

from src.utils.time_utils import is_market_open, get_current_et_time, is_trading_day, ET


class TestIsMarketOpen:
    """Tests for is_market_open function."""

    def test_weekday_during_market_hours(self):
        """Monday at noon ET should be open."""
        monday_noon = ET.localize(datetime(2026, 2, 2, 12, 0))  # Monday
        is_open, message = is_market_open(monday_noon)
        assert is_open is True
        assert "open" in message.lower()

    def test_weekday_before_market_open(self):
        """Monday at 9:00 AM should be closed."""
        monday_early = ET.localize(datetime(2026, 2, 2, 9, 0))  # Before 9:30
        is_open, message = is_market_open(monday_early)
        assert is_open is False
        assert "outside market hours" in message.lower()

    def test_weekday_after_market_close(self):
        """Monday at 5:00 PM should be closed."""
        monday_late = ET.localize(datetime(2026, 2, 2, 17, 0))  # After 4:00 PM
        is_open, message = is_market_open(monday_late)
        assert is_open is False
        assert "outside market hours" in message.lower()

    def test_saturday_returns_closed(self):
        """Saturday should be closed."""
        saturday = ET.localize(datetime(2026, 1, 31, 12, 0))  # Saturday
        is_open, message = is_market_open(saturday)
        assert is_open is False
        assert "weekend" in message.lower()

    def test_sunday_returns_closed(self):
        """Sunday should be closed."""
        sunday = ET.localize(datetime(2026, 2, 1, 12, 0))  # Sunday
        is_open, message = is_market_open(sunday)
        assert is_open is False
        assert "weekend" in message.lower()

    def test_market_open_boundary(self):
        """9:30 AM exactly should be open."""
        monday_930 = ET.localize(datetime(2026, 2, 2, 9, 30))
        is_open, message = is_market_open(monday_930)
        assert is_open is True

    def test_market_close_boundary(self):
        """4:00 PM exactly should be open."""
        monday_400 = ET.localize(datetime(2026, 2, 2, 16, 0))
        is_open, message = is_market_open(monday_400)
        assert is_open is True

    def test_one_minute_after_close(self):
        """4:01 PM should be closed."""
        monday_401 = ET.localize(datetime(2026, 2, 2, 16, 1))
        is_open, message = is_market_open(monday_401)
        assert is_open is False


class TestGetCurrentETTime:
    """Tests for get_current_et_time function."""

    def test_returns_datetime_with_timezone(self):
        """Should return datetime with ET timezone."""
        now = get_current_et_time()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None
        tz_name = str(now.tzinfo)
        assert any(x in tz_name for x in ["EST", "EDT", "Eastern"])

    def test_returns_current_time(self):
        """Should return time close to actual current time."""
        before = datetime.now(ET)
        now = get_current_et_time()
        after = datetime.now(ET)
        assert before <= now <= after


class TestIsTradingDay:
    """Tests for is_trading_day function."""

    def test_monday_is_trading_day(self):
        """Monday should be a trading day."""
        monday = datetime(2026, 2, 2)  # Monday
        assert is_trading_day(monday) is True

    def test_friday_is_trading_day(self):
        """Friday should be a trading day."""
        friday = datetime(2026, 2, 6)  # Friday
        assert is_trading_day(friday) is True

    def test_saturday_not_trading_day(self):
        """Saturday should not be a trading day."""
        saturday = datetime(2026, 1, 31)  # Saturday
        assert is_trading_day(saturday) is False

    def test_sunday_not_trading_day(self):
        """Sunday should not be a trading day."""
        sunday = datetime(2026, 2, 1)  # Sunday
        assert is_trading_day(sunday) is False
