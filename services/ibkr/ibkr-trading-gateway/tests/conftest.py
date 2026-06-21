"""Pytest configuration and shared fixtures."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock

from src.models.trade_request import AnalysisData, TradeRequest


@pytest.fixture
def sample_analysis_data() -> AnalysisData:
    """Sample analysis data for testing."""
    return AnalysisData(
        win_probability=0.65,
        expected_gain_pct=0.15,
        expected_loss_pct=-0.07,
        confidence=0.85,
    )


@pytest.fixture
def sample_trade_request(sample_analysis_data) -> TradeRequest:
    """Sample trade request for testing."""
    return TradeRequest(
        request_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        action="BUY",
        analysis=sample_analysis_data,
        reasoning="Test trade for unit testing",
    )


@pytest.fixture
def sample_trade_request_dict(sample_analysis_data) -> dict:
    """Sample trade request as dict (for JSON deserialization tests)."""
    return {
        "request_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": "aapl",  # lowercase to test uppercase conversion
        "action": "BUY",
        "analysis": {
            "win_probability": 0.65,
            "expected_gain_pct": 0.15,
            "expected_loss_pct": -0.07,
            "confidence": 0.85,
        },
        "reasoning": "Test trade",
    }


@pytest.fixture
def mock_ib_connection():
    """Mock IBKR connection for testing."""
    mock = Mock()
    mock.is_connected.return_value = True
    mock.get_account_value.return_value = 1000.0
    mock.cancel_all_orders.return_value = 0
    return mock


@pytest.fixture
def mock_db_adapter():
    """Mock database adapter for testing."""
    mock = Mock()
    mock.get_today_trade_count.return_value = 0
    mock.get_week_trade_count.return_value = 0
    mock.get_daily_pnl_percent.return_value = 0.0
    mock.get_recent_trade.return_value = None
    return mock


@pytest.fixture
def mock_discord_notifier():
    """Mock Discord notifier for testing."""
    mock = Mock()
    return mock
