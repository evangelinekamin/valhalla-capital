"""Unit tests for Risk Validator (TDD - safety critical!)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.services.risk_validator import RiskValidator, RiskCheck, RiskCheckStatus
from config.settings import Settings


class TestRiskValidator:
    """Tests for multi-layer risk validation."""

    @pytest.fixture
    def mock_db(self):
        """Mock database adapter."""
        mock = Mock()
        mock.get_today_trade_count.return_value = 0
        mock.get_week_trade_count.return_value = 0
        mock.get_daily_pnl_percent.return_value = 0.0
        mock.get_recent_trade.return_value = None
        return mock

    @pytest.fixture
    def mock_ib(self):
        """Mock IBKR connection."""
        mock = Mock()
        mock.get_account_value.return_value = 1000.0  # $1000 portfolio
        return mock

    @pytest.fixture
    def validator(self, mock_db, mock_ib):
        """Risk validator with mocked dependencies."""
        settings = Settings(
            max_position_fraction=0.20,
            max_daily_loss_pct=0.03,
            max_trades_per_day=10,
            max_trades_per_week=30,
        )
        return RiskValidator(db=mock_db, ib=mock_ib, settings=settings)

    # Market Hours Tests
    def test_rejects_weekend_trades(self, validator):
        """Should reject trades on Saturday."""
        saturday = datetime(2026, 1, 31, 12, 0)  # Saturday
        with patch("src.utils.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            checks = validator.validate(
                ticker="AAPL", action="BUY", quantity=10, current_price=150.0
            )

        market_check = next((c for c in checks if c.name == "market_hours"), None)
        assert market_check is not None
        assert market_check.status == RiskCheckStatus.REJECTED
        assert "weekend" in market_check.message.lower()

    def test_approves_market_hours_trades(self, validator):
        """Should approve trades during market hours."""
        from src.utils.time_utils import ET

        monday_noon = ET.localize(datetime(2026, 2, 2, 12, 0))  # Monday noon
        with patch("src.utils.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = monday_noon
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            checks = validator.validate(
                ticker="AAPL", action="BUY", quantity=1, current_price=150.0
            )

        market_check = next(c for c in checks if c.name == "market_hours")
        assert market_check.status == RiskCheckStatus.APPROVED

    # Daily Trade Limit Tests
    def test_rejects_exceeding_daily_limit(self, validator, mock_db):
        """Should reject when daily trade limit reached."""
        mock_db.get_today_trade_count.return_value = 10  # At limit
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        daily_check = next(c for c in checks if c.name == "daily_trade_limit")
        assert daily_check.status == RiskCheckStatus.REJECTED
        assert "limit reached" in daily_check.message.lower()

    def test_warns_approaching_daily_limit(self, validator, mock_db):
        """Should warn when approaching daily limit (80%)."""
        mock_db.get_today_trade_count.return_value = 8  # 80% of 10
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        daily_check = next(c for c in checks if c.name == "daily_trade_limit")
        assert daily_check.status == RiskCheckStatus.WARNING
        assert "approaching" in daily_check.message.lower()

    # Weekly Trade Limit Tests
    def test_rejects_exceeding_weekly_limit(self, validator, mock_db):
        """Should reject when weekly trade limit reached."""
        mock_db.get_week_trade_count.return_value = 30  # At limit
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        weekly_check = next(c for c in checks if c.name == "weekly_trade_limit")
        assert weekly_check.status == RiskCheckStatus.REJECTED

    # Position Size Tests
    def test_rejects_oversized_position(self, validator):
        """Should reject positions exceeding max fraction."""
        # $1000 portfolio, 20% max = $200 max position
        # 3 shares @ $100 = $300 > $200
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=3, current_price=100.0
        )

        size_check = next(c for c in checks if c.name == "position_size")
        assert size_check.status == RiskCheckStatus.REJECTED
        assert "exceeds max" in size_check.message.lower()

    def test_approves_acceptable_position_size(self, validator):
        """Should approve positions within limits."""
        # $1000 portfolio, 20% max = $200 max
        # 1 share @ $150 = $150 < $200
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=150.0
        )

        size_check = next(c for c in checks if c.name == "position_size")
        assert size_check.status == RiskCheckStatus.APPROVED

    # Daily Loss Limit Tests
    def test_rejects_after_daily_loss_limit(self, validator, mock_db):
        """Should reject trades when daily loss exceeds limit."""
        mock_db.get_daily_pnl_percent.return_value = -0.04  # 4% loss (over 3% limit)
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        loss_check = next(c for c in checks if c.name == "daily_loss_limit")
        assert loss_check.status == RiskCheckStatus.REJECTED
        assert "exceeds limit" in loss_check.message.lower()

    def test_approves_within_daily_loss_limit(self, validator, mock_db):
        """Should approve when daily loss is acceptable."""
        mock_db.get_daily_pnl_percent.return_value = -0.02  # 2% loss (under 3% limit)
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        loss_check = next(c for c in checks if c.name == "daily_loss_limit")
        assert loss_check.status == RiskCheckStatus.APPROVED

    # Duplicate Trade Tests
    def test_warns_on_duplicate_trade(self, validator, mock_db):
        """Should warn on similar trades within 30 minutes."""
        mock_db.get_recent_trade.return_value = {"action": "BUY", "minutes_ago": 15}
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        dup_check = next(c for c in checks if c.name == "duplicate_trade")
        assert dup_check.status == RiskCheckStatus.WARNING
        assert "minutes ago" in dup_check.message.lower()

    def test_approves_no_duplicate_trades(self, validator, mock_db):
        """Should approve when no recent duplicates."""
        mock_db.get_recent_trade.return_value = None
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        dup_check = next(c for c in checks if c.name == "duplicate_trade")
        assert dup_check.status == RiskCheckStatus.APPROVED

    # Account Balance Tests
    def test_rejects_insufficient_funds(self, validator, mock_ib):
        """Should reject when insufficient buying power."""
        mock_ib.get_account_value.return_value = 50.0  # Only $50 available
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=10, current_price=100.0  # Need $1050
        )

        balance_check = next(c for c in checks if c.name == "account_balance")
        assert balance_check.status == RiskCheckStatus.REJECTED
        assert "insufficient" in balance_check.message.lower()

    def test_approves_sufficient_funds(self, validator, mock_ib):
        """Should approve when sufficient funds available."""
        mock_ib.get_account_value.return_value = 1000.0
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=100.0  # Need $105
        )

        balance_check = next(c for c in checks if c.name == "account_balance")
        assert balance_check.status == RiskCheckStatus.APPROVED

    # Portfolio Concentration Tests
    def test_portfolio_concentration_check_exists(self, validator):
        """Should include portfolio concentration check."""
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        conc_check = next((c for c in checks if c.name == "portfolio_concentration"), None)
        assert conc_check is not None

    # Aggregate Validation Tests
    def test_is_approved_true_when_all_pass(self, validator):
        """Trade should be approved when all checks pass."""
        from src.utils.time_utils import ET

        monday_noon = ET.localize(datetime(2026, 2, 2, 12, 0))
        with patch("src.utils.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = monday_noon
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            checks = validator.validate(
                ticker="AAPL", action="BUY", quantity=1, current_price=100.0
            )

        assert validator.is_approved(checks) is True

    def test_is_approved_false_if_any_rejected(self, validator, mock_db):
        """Trade should not be approved if any check fails."""
        mock_db.get_today_trade_count.return_value = 15  # Over limit
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        assert validator.is_approved(checks) is False

    def test_warnings_do_not_block_approval(self, validator, mock_db):
        """Warnings should not prevent trade approval."""
        from src.utils.time_utils import ET

        # Set up warning condition (approaching daily limit)
        mock_db.get_today_trade_count.return_value = 8
        mock_db.get_recent_trade.return_value = {"action": "BUY", "minutes_ago": 20}

        monday_noon = ET.localize(datetime(2026, 2, 2, 12, 0))
        with patch("src.utils.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = monday_noon
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            checks = validator.validate(
                ticker="AAPL", action="BUY", quantity=1, current_price=100.0
            )

        # Should have warnings but still be approved
        warnings = [c for c in checks if c.status == RiskCheckStatus.WARNING]
        assert len(warnings) > 0
        assert validator.is_approved(checks) is True

    def test_all_eight_checks_performed(self, validator):
        """Should perform all 8 risk checks."""
        checks = validator.validate(
            ticker="AAPL", action="BUY", quantity=1, current_price=10.0
        )

        check_names = {c.name for c in checks}
        expected_checks = {
            "market_hours",
            "daily_trade_limit",
            "weekly_trade_limit",
            "position_size",
            "portfolio_concentration",
            "daily_loss_limit",
            "duplicate_trade",
            "account_balance",
        }

        assert check_names == expected_checks
