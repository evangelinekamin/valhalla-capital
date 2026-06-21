"""Unit tests for TradeResult Pydantic model."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from src.models.trade_result import (
    TradeExecution,
    KellyResult,
    RiskCheckResult,
    TradeResult,
)


class TestTradeExecution:
    """Tests for TradeExecution model."""

    def test_valid_filled_execution(self):
        """Valid filled execution should parse correctly."""
        exec = TradeExecution(
            ticker="AAPL",
            action="BUY",
            quantity=10,
            status="FILLED",
            filled_price=150.50,
            commission=1.00,
            order_id=12345,
        )
        assert exec.ticker == "AAPL"
        assert exec.status == "FILLED"
        assert exec.filled_price == 150.50

    def test_rejected_execution_no_price(self):
        """Rejected execution should allow None for price/commission."""
        exec = TradeExecution(
            ticker="AAPL",
            action="BUY",
            quantity=0,
            status="REJECTED",
            filled_price=None,
            commission=None,
            order_id=None,
        )
        assert exec.status == "REJECTED"
        assert exec.filled_price is None

    def test_negative_quantity_rejected(self):
        """Negative quantity should be rejected."""
        with pytest.raises(ValidationError):
            TradeExecution(
                ticker="AAPL",
                action="BUY",
                quantity=-5,  # Invalid
                status="FILLED",
            )


class TestKellyResult:
    """Tests for KellyResult model."""

    def test_valid_kelly_result(self):
        """Valid Kelly result should parse correctly."""
        kelly = KellyResult(
            kelly_fraction=0.185,
            half_kelly_fraction=0.0925,
            position_size_usd=150.00,
            position_size_shares=1,
        )
        assert kelly.half_kelly_fraction == kelly.kelly_fraction * 0.5
        assert kelly.position_size_shares == 1

    def test_zero_position(self):
        """Zero position size should be valid (negative edge)."""
        kelly = KellyResult(
            kelly_fraction=-0.02,
            half_kelly_fraction=0.0,
            position_size_usd=0.0,
            position_size_shares=0,
        )
        assert kelly.position_size_usd == 0.0
        assert kelly.position_size_shares == 0

    def test_negative_position_size_rejected(self):
        """Negative position size should be rejected."""
        with pytest.raises(ValidationError):
            KellyResult(
                kelly_fraction=0.1,
                half_kelly_fraction=0.05,
                position_size_usd=-100.0,  # Invalid
                position_size_shares=0,
            )


class TestRiskCheckResult:
    """Tests for RiskCheckResult model."""

    def test_passed_risk_check(self):
        """Passed risk check should parse correctly."""
        check = RiskCheckResult(
            name="market_hours", passed=True, message="Market is open"
        )
        assert check.passed is True
        assert check.name == "market_hours"

    def test_failed_risk_check(self):
        """Failed risk check should parse correctly."""
        check = RiskCheckResult(
            name="daily_loss_limit",
            passed=False,
            message="Daily loss limit exceeded",
        )
        assert check.passed is False


class TestTradeResult:
    """Tests for TradeResult model."""

    def test_approved_trade_result(self):
        """Approved trade with execution should be valid."""
        result = TradeResult(
            request_id=uuid4(),
            processed_at=datetime.now(timezone.utc),
            approved=True,
            trade_result=TradeExecution(
                ticker="AAPL",
                action="BUY",
                quantity=10,
                status="FILLED",
                filled_price=150.50,
                commission=1.00,
                order_id=12345,
            ),
            risk_checks=[
                RiskCheckResult(
                    name="market_hours", passed=True, message="Market open"
                )
            ],
            kelly_calculation=KellyResult(
                kelly_fraction=0.185,
                half_kelly_fraction=0.0925,
                position_size_usd=150.00,
                position_size_shares=1,
            ),
            message="Trade executed successfully",
        )
        assert result.approved is True
        assert result.trade_result is not None
        assert result.kelly_calculation is not None

    def test_rejected_trade_result(self):
        """Rejected trade should have no execution details."""
        result = TradeResult(
            request_id=uuid4(),
            processed_at=datetime.now(timezone.utc),
            approved=False,
            trade_result=None,
            risk_checks=[
                RiskCheckResult(
                    name="daily_loss_limit",
                    passed=False,
                    message="Daily loss exceeded",
                )
            ],
            kelly_calculation=None,
            message="Trade rejected due to risk limits",
        )
        assert result.approved is False
        assert result.trade_result is None

    def test_json_serialization(self):
        """TradeResult should serialize to JSON."""
        result = TradeResult(
            request_id=uuid4(),
            processed_at=datetime.now(timezone.utc),
            approved=True,
            trade_result=TradeExecution(
                ticker="AAPL",
                action="BUY",
                quantity=10,
                status="FILLED",
                filled_price=150.50,
                commission=1.00,
            ),
            risk_checks=[],
            kelly_calculation=KellyResult(
                kelly_fraction=0.185,
                half_kelly_fraction=0.0925,
                position_size_usd=150.00,
                position_size_shares=1,
            ),
            message="Success",
        )
        json_str = result.model_dump_json()
        assert "AAPL" in json_str
        assert "FILLED" in json_str

    def test_empty_risk_checks(self):
        """Empty risk checks list should be valid."""
        result = TradeResult(
            request_id=uuid4(),
            processed_at=datetime.now(timezone.utc),
            approved=False,
            risk_checks=[],  # Empty is valid
            message="No checks performed",
        )
        assert result.risk_checks == []

    def test_immutable(self):
        """TradeResult should be immutable."""
        result = TradeResult(
            request_id=uuid4(),
            processed_at=datetime.now(timezone.utc),
            approved=True,
            message="Test",
        )
        with pytest.raises(ValidationError):
            result.approved = False
