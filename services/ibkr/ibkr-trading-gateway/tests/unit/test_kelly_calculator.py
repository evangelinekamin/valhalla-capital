"""Unit tests for Kelly Calculator (TDD - tests first!)."""
import pytest

from src.services.kelly_calculator import KellyCalculator, KellyInputs, KellyResult
from config.settings import Settings


class TestKellyCalculator:
    """Tests for Kelly Criterion position sizing."""

    @pytest.fixture
    def calculator(self):
        """Calculator with $1000 portfolio."""
        settings = Settings(
            min_position_size_usd=30.0,
            max_position_size_usd=2000.0,
            max_position_fraction=0.20,
        )
        return KellyCalculator(portfolio_value=1000.0, settings=settings)

    @pytest.fixture
    def small_calculator(self):
        """Calculator with $200 portfolio (small capital)."""
        settings = Settings(
            min_position_size_usd=30.0,
            max_position_size_usd=2000.0,
            max_position_fraction=0.20,
        )
        return KellyCalculator(portfolio_value=200.0, settings=settings)

    def test_positive_edge_returns_positive_fraction(self, calculator):
        """With positive expected value, Kelly should be positive."""
        inputs = KellyInputs(
            win_rate=0.60, avg_win_pct=0.10, avg_loss_pct=-0.05, confidence=1.0
        )
        result = calculator.calculate(inputs, current_price=100.0)

        assert result.kelly_fraction > 0
        assert result.half_kelly_fraction == result.kelly_fraction * 0.5
        assert result.position_size_shares >= 0

    def test_negative_edge_returns_zero(self, calculator):
        """With negative expected value, should not trade."""
        inputs = KellyInputs(
            win_rate=0.40,  # Low win rate
            avg_win_pct=0.10,
            avg_loss_pct=-0.15,  # Large losses
            confidence=1.0,
        )
        result = calculator.calculate(inputs, current_price=100.0)

        assert result.kelly_fraction <= 0
        assert result.position_size_usd == 0
        assert result.position_size_shares == 0
        assert len(result.warnings) > 0
        assert "negative" in result.warnings[0].lower() or "edge" in result.warnings[0].lower()

    def test_caps_at_max_position_fraction(self, calculator):
        """Even with high Kelly, should cap at MAX_POSITION_FRACTION."""
        inputs = KellyInputs(
            win_rate=0.90,  # Very high
            avg_win_pct=0.50,  # Large wins
            avg_loss_pct=-0.05,  # Small losses
            confidence=1.0,
        )
        result = calculator.calculate(inputs, current_price=10.0)

        # $1000 * 20% max = $200 max position
        assert result.position_size_usd <= 200.0
        assert any("cap" in w.lower() for w in result.warnings)

    def test_respects_min_position_size(self, small_calculator):
        """Positions below minimum should be zeroed."""
        inputs = KellyInputs(
            win_rate=0.52,  # Slight edge
            avg_win_pct=0.03,  # Small wins
            avg_loss_pct=-0.03,  # Small losses
            confidence=1.0,
        )
        result = small_calculator.calculate(inputs, current_price=50.0)

        # If calculated position < $30 minimum, should be 0
        if result.position_size_usd > 0:
            assert result.position_size_usd >= 30.0
        else:
            assert any("minimum" in w.lower() for w in result.warnings)

    def test_respects_max_position_size(self):
        """Position should not exceed absolute max."""
        settings = Settings(
            min_position_size_usd=30.0,
            max_position_size_usd=500.0,  # Lower max for testing
            max_position_fraction=0.50,  # High fraction
        )
        calculator = KellyCalculator(portfolio_value=10000.0, settings=settings)

        inputs = KellyInputs(
            win_rate=0.80,
            avg_win_pct=0.30,
            avg_loss_pct=-0.05,
            confidence=1.0,
        )
        result = calculator.calculate(inputs, current_price=10.0)

        # Should cap at $500 even though portfolio allows more
        assert result.position_size_usd <= 500.0

    def test_confidence_adjustment_reduces_position(self, calculator):
        """Lower confidence should reduce position size."""
        inputs_high = KellyInputs(
            win_rate=0.65,
            avg_win_pct=0.15,
            avg_loss_pct=-0.07,
            confidence=1.0,
        )
        inputs_low = KellyInputs(
            win_rate=0.65,
            avg_win_pct=0.15,
            avg_loss_pct=-0.07,
            confidence=0.5,  # Half confidence
        )

        result_high = calculator.calculate(inputs_high, current_price=100.0)
        result_low = calculator.calculate(inputs_low, current_price=100.0)

        assert result_low.position_size_usd < result_high.position_size_usd

    def test_calculates_correct_share_count(self, calculator):
        """Share count should be floor of position_usd / price."""
        inputs = KellyInputs(
            win_rate=0.65, avg_win_pct=0.15, avg_loss_pct=-0.07, confidence=1.0
        )
        price = 33.33
        result = calculator.calculate(inputs, current_price=price)

        if result.position_size_usd > 0:
            expected_shares = int(result.position_size_usd / price)
            assert result.position_size_shares == expected_shares
            # Actual USD should be shares * price
            assert result.position_size_usd == result.position_size_shares * price

    def test_high_price_may_result_in_zero_shares(self, small_calculator):
        """Very high share price may result in zero shares."""
        inputs = KellyInputs(
            win_rate=0.60, avg_win_pct=0.10, avg_loss_pct=-0.05, confidence=1.0
        )
        result = small_calculator.calculate(inputs, current_price=500.0)

        # Small portfolio, high price -> likely zero shares
        if result.position_size_shares == 0 and result.position_size_usd > 0:
            assert any("price" in w.lower() for w in result.warnings)

    def test_kelly_formula_correctness(self, calculator):
        """Verify Kelly formula: f = (p*W - (1-p)*L) / W."""
        inputs = KellyInputs(
            win_rate=0.60, avg_win_pct=0.20, avg_loss_pct=-0.10, confidence=1.0
        )
        result = calculator.calculate(inputs, current_price=100.0)

        # Manual calculation
        p = 0.60
        W = 0.20
        L = 0.10
        expected_kelly = (p * W - (1 - p) * L) / W

        assert abs(result.kelly_fraction - expected_kelly) < 0.0001

    def test_zero_confidence_zeros_position(self, calculator):
        """Zero confidence should result in zero position."""
        inputs = KellyInputs(
            win_rate=0.70,
            avg_win_pct=0.20,
            avg_loss_pct=-0.05,
            confidence=0.0,  # No confidence
        )
        result = calculator.calculate(inputs, current_price=100.0)

        assert result.position_size_usd == 0
        assert result.position_size_shares == 0

    def test_default_confidence_is_one(self):
        """KellyInputs should default confidence to 1.0."""
        inputs = KellyInputs(win_rate=0.6, avg_win_pct=0.1, avg_loss_pct=-0.05)
        assert inputs.confidence == 1.0

    def test_warnings_list_populated(self, calculator):
        """Warnings should be populated for various conditions."""
        # Test with oversized Kelly
        inputs = KellyInputs(
            win_rate=0.90, avg_win_pct=0.50, avg_loss_pct=-0.05, confidence=1.0
        )
        result = calculator.calculate(inputs, current_price=10.0)

        assert isinstance(result.warnings, list)
        if result.position_size_usd < 200:  # Capped
            assert len(result.warnings) > 0
