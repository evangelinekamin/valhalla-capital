"""Unit tests for TradeRequest Pydantic model."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from src.models.trade_request import AnalysisData, TradeRequest


class TestAnalysisData:
    """Tests for AnalysisData model."""

    def test_valid_analysis_data(self):
        """Valid analysis data should parse correctly."""
        data = AnalysisData(
            win_probability=0.65,
            expected_gain_pct=0.15,
            expected_loss_pct=-0.07,
            confidence=0.85,
        )
        assert data.win_probability == 0.65
        assert data.expected_gain_pct == 0.15
        assert data.expected_loss_pct == -0.07
        assert data.confidence == 0.85

    def test_default_confidence(self):
        """Confidence should default to 0.8."""
        data = AnalysisData(
            win_probability=0.6, expected_gain_pct=0.1, expected_loss_pct=-0.05
        )
        assert data.confidence == 0.8

    def test_win_probability_out_of_range(self):
        """Win probability > 1.0 should be rejected."""
        with pytest.raises(ValidationError) as exc:
            AnalysisData(
                win_probability=1.5,  # Invalid
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            )
        assert "win_probability" in str(exc.value)

    def test_negative_win_probability(self):
        """Negative win probability should be rejected."""
        with pytest.raises(ValidationError):
            AnalysisData(
                win_probability=-0.1,  # Invalid
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            )

    def test_positive_loss_percentage(self):
        """Expected loss must be negative."""
        with pytest.raises(ValidationError) as exc:
            AnalysisData(
                win_probability=0.6,
                expected_gain_pct=0.15,
                expected_loss_pct=0.07,  # Invalid: must be negative
            )
        assert "expected_loss_pct" in str(exc.value)

    def test_negative_gain_percentage(self):
        """Expected gain must be positive."""
        with pytest.raises(ValidationError) as exc:
            AnalysisData(
                win_probability=0.6,
                expected_gain_pct=-0.15,  # Invalid: must be positive
                expected_loss_pct=-0.07,
            )
        assert "expected_gain_pct" in str(exc.value)

    def test_immutable(self):
        """AnalysisData should be immutable."""
        data = AnalysisData(
            win_probability=0.6, expected_gain_pct=0.1, expected_loss_pct=-0.05
        )
        with pytest.raises(ValidationError):
            data.win_probability = 0.7


class TestTradeRequest:
    """Tests for TradeRequest model."""

    def test_valid_trade_request(self):
        """Valid trade request should parse correctly."""
        request = TradeRequest(
            request_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            ticker="AAPL",
            action="BUY",
            analysis=AnalysisData(
                win_probability=0.65,
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            ),
            reasoning="Strong technical setup",
        )
        assert request.ticker == "AAPL"
        assert request.action == "BUY"

    def test_ticker_uppercase_conversion(self):
        """Lowercase ticker should be converted to uppercase."""
        request = TradeRequest(
            request_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            ticker="aapl",  # lowercase
            action="BUY",
            analysis=AnalysisData(
                win_probability=0.65,
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            ),
            reasoning="Test",
        )
        assert request.ticker == "AAPL"  # Should be uppercase

    def test_ticker_whitespace_stripped(self):
        """Whitespace in ticker should be stripped."""
        request = TradeRequest(
            request_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            ticker=" AAPL ",
            action="BUY",
            analysis=AnalysisData(
                win_probability=0.65,
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            ),
            reasoning="Test",
        )
        assert request.ticker == "AAPL"

    def test_invalid_action(self):
        """Action must be BUY or SELL."""
        with pytest.raises(ValidationError):
            TradeRequest(
                request_id=uuid4(),
                timestamp=datetime.now(timezone.utc),
                ticker="AAPL",
                action="HOLD",  # Invalid
                analysis=AnalysisData(
                    win_probability=0.65,
                    expected_gain_pct=0.15,
                    expected_loss_pct=-0.07,
                ),
                reasoning="Test",
            )

    def test_empty_ticker(self):
        """Empty ticker should be rejected."""
        with pytest.raises(ValidationError):
            TradeRequest(
                request_id=uuid4(),
                timestamp=datetime.now(timezone.utc),
                ticker="",  # Invalid
                action="BUY",
                analysis=AnalysisData(
                    win_probability=0.65,
                    expected_gain_pct=0.15,
                    expected_loss_pct=-0.07,
                ),
                reasoning="Test",
            )

    def test_ticker_too_long(self):
        """Ticker longer than 10 characters should be rejected."""
        with pytest.raises(ValidationError):
            TradeRequest(
                request_id=uuid4(),
                timestamp=datetime.now(timezone.utc),
                ticker="TOOLONGTICKER",  # Invalid: > 10 chars
                action="BUY",
                analysis=AnalysisData(
                    win_probability=0.65,
                    expected_gain_pct=0.15,
                    expected_loss_pct=-0.07,
                ),
                reasoning="Test",
            )

    def test_json_serialization(self):
        """TradeRequest should serialize to JSON."""
        request = TradeRequest(
            request_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            ticker="AAPL",
            action="BUY",
            analysis=AnalysisData(
                win_probability=0.65,
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            ),
            reasoning="Test",
        )
        json_str = request.model_dump_json()
        assert "AAPL" in json_str
        assert "BUY" in json_str

    def test_json_deserialization(self):
        """TradeRequest should deserialize from JSON."""
        data = {
            "request_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": "aapl",
            "action": "BUY",
            "analysis": {
                "win_probability": 0.65,
                "expected_gain_pct": 0.15,
                "expected_loss_pct": -0.07,
                "confidence": 0.85,
            },
            "reasoning": "Test",
        }
        request = TradeRequest.model_validate(data)
        assert request.ticker == "AAPL"
        assert request.analysis.confidence == 0.85

    def test_immutable(self):
        """TradeRequest should be immutable."""
        request = TradeRequest(
            request_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            ticker="AAPL",
            action="BUY",
            analysis=AnalysisData(
                win_probability=0.65,
                expected_gain_pct=0.15,
                expected_loss_pct=-0.07,
            ),
            reasoning="Test",
        )
        with pytest.raises(ValidationError):
            request.ticker = "MSFT"
