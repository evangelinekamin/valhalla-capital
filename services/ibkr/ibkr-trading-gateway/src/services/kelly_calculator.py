"""Kelly Criterion position sizing calculator with Half-Kelly approach."""
from dataclasses import dataclass
from typing import List

import structlog

from config.settings import Settings

log = structlog.get_logger()


@dataclass
class KellyInputs:
    """Inputs for Kelly Criterion calculation."""

    win_rate: float  # 0.0 to 1.0
    avg_win_pct: float  # Average winning trade return (e.g., 0.15 for 15%)
    avg_loss_pct: float  # Average losing trade return (e.g., -0.08 for 8% loss)
    confidence: float = 1.0  # Informational only, not applied to Kelly


@dataclass
class KellyResult:
    """Result of Kelly Criterion position sizing."""

    kelly_fraction: float
    half_kelly_fraction: float
    position_size_usd: float
    position_size_shares: float
    warnings: List[str]


class KellyCalculator:
    """
    Calculates position sizes using Half-Kelly Criterion.

    The Kelly Criterion optimizes position sizing based on win rate and
    average win/loss percentages. We use Half-Kelly for reduced volatility.

    Formula: f = (p*W - (1-p)*L) / W
    where:
        p = win probability
        W = average win %
        L = average loss % (as positive number)

    Note: Confidence is NOT applied as a multiplier to the Kelly fraction.
    The Overseer handles confidence-based adjustments in its own sizing.
    This calculator produces a pure Kelly result as a fallback only.
    """

    def __init__(self, portfolio_value: float, settings: Settings | None = None):
        """
        Initialize Kelly calculator.

        Args:
            portfolio_value: Current portfolio value in USD
            settings: Application settings (uses defaults if None)
        """
        self.portfolio_value = portfolio_value
        self.settings = settings or Settings()
        self.logger = log.bind(component="kelly_calculator")

    def calculate(self, inputs: KellyInputs, current_price: float) -> KellyResult:
        """
        Calculate position size using Half-Kelly Criterion.

        Args:
            inputs: Kelly calculation inputs
            current_price: Current share price

        Returns:
            KellyResult with calculated size and warnings
        """
        warnings = []

        # Extract values
        p = inputs.win_rate
        W = inputs.avg_win_pct
        L = abs(inputs.avg_loss_pct)

        # Calculate full Kelly fraction: f = (p*W - (1-p)*L) / W
        kelly_fraction = (p * W - (1 - p) * L) / W

        # Check if Kelly is negative (negative edge)
        if kelly_fraction <= 0:
            warnings.append(
                f"Negative Kelly fraction ({kelly_fraction:.4f}) - no edge detected"
            )
            self.logger.info(
                "negative_kelly",
                kelly=kelly_fraction,
                win_rate=p,
                avg_win=W,
                avg_loss=-L,
            )
            return KellyResult(
                kelly_fraction=kelly_fraction,
                half_kelly_fraction=0.0,
                position_size_usd=0.0,
                position_size_shares=0,
                warnings=warnings,
            )

        # Apply Half-Kelly
        half_kelly = kelly_fraction * 0.5

        # Check against maximum position fraction
        max_fraction = self.settings.max_position_fraction
        if half_kelly > max_fraction:
            warnings.append(
                f"Half-Kelly ({half_kelly:.2%}) exceeds max ({max_fraction:.2%}), "
                f"capping position size"
            )
            half_kelly = max_fraction

        # Calculate dollar amount
        position_size_usd = self.portfolio_value * half_kelly

        # Apply absolute dollar limits
        min_size = self.settings.min_position_size_usd
        max_size = self.settings.max_position_size_usd

        if position_size_usd < min_size:
            warnings.append(
                f"Position size ${position_size_usd:.2f} below minimum ${min_size}, "
                f"skipping trade"
            )
            position_size_usd = 0.0

        if position_size_usd > max_size:
            warnings.append(
                f"Position size ${position_size_usd:.2f} exceeds maximum ${max_size}, "
                f"capping at max"
            )
            position_size_usd = max_size

        # Calculate number of shares (round to nearest, supports fractional)
        shares = round(position_size_usd / current_price, 4) if position_size_usd > 0 else 0
        actual_position_usd = shares * current_price

        if shares == 0 and position_size_usd > 0:
            warnings.append(
                f"Share price ${current_price:.2f} too high for position size "
                f"${position_size_usd:.2f}"
            )

        self.logger.info(
            "kelly_calculated",
            kelly=kelly_fraction,
            half_kelly=half_kelly,
            position_usd=actual_position_usd,
            shares=shares,
            warnings=len(warnings),
        )

        return KellyResult(
            kelly_fraction=kelly_fraction,
            half_kelly_fraction=half_kelly,
            position_size_usd=actual_position_usd,
            position_size_shares=shares,
            warnings=warnings,
        )

    def update_portfolio_value(self, new_value: float) -> None:
        """
        Update portfolio value for subsequent calculations.

        Args:
            new_value: New portfolio value in USD
        """
        self.portfolio_value = new_value
        self.logger.info("portfolio_value_updated", new_value=new_value)
