"""Corporate events models - dividends, splits, earnings."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import Field

from .base import FMPBaseModel


class DividendRecord(FMPBaseModel):
    """Historical dividend record."""

    symbol: str = Field(..., description="Stock ticker symbol")
    dividend_date: date = Field(..., alias="date", description="Declaration date")
    label: Optional[str] = Field(None, description="Label (e.g., 'Q1 2024')")
    adj_dividend: float = Field(
        ...,
        alias="adjDividend",
        description="Adjusted dividend amount"
    )
    dividend: float = Field(..., description="Dividend amount")
    record_date: Optional[date] = Field(
        None,
        alias="recordDate",
        description="Record date"
    )
    payment_date: Optional[date] = Field(
        None,
        alias="paymentDate",
        description="Payment date"
    )
    declaration_date: Optional[date] = Field(
        None,
        alias="declarationDate",
        description="Declaration date"
    )


class StockSplit(FMPBaseModel):
    """Stock split event."""

    symbol: str = Field(..., description="Stock ticker symbol")
    split_date: date = Field(..., alias="date", description="Split date")
    label: Optional[str] = Field(None, description="Split label")

    # Split ratio
    numerator: float = Field(..., description="Split numerator")
    denominator: float = Field(..., description="Split denominator")

    @property
    def ratio(self) -> float:
        """Calculate split ratio.

        Returns:
            Split ratio (numerator / denominator)
        """
        return self.numerator / self.denominator

    @property
    def ratio_formatted(self) -> str:
        """Get formatted ratio string.

        Returns:
            Formatted ratio (e.g., "2-for-1", "3-for-2")
        """
        return f"{int(self.numerator)}-for-{int(self.denominator)}"


class EarningsEvent(FMPBaseModel):
    """Earnings event from earnings calendar."""

    symbol: str = Field(..., description="Stock ticker symbol")
    earnings_date: date = Field(..., alias="date", description="Earnings date")

    # Estimates
    eps_estimated: Optional[float] = Field(
        None,
        alias="epsEstimated",
        description="Estimated EPS"
    )
    eps: Optional[float] = Field(None, description="Actual EPS")
    revenue_estimated: Optional[float] = Field(
        None,
        alias="revenueEstimated",
        description="Estimated revenue"
    )
    revenue: Optional[float] = Field(None, description="Actual revenue")

    # Timing
    time: Optional[str] = Field(
        None,
        description="Time of earnings (e.g., 'bmo', 'amc')"
    )

    # Fiscal period
    fiscal_date_ending: Optional[date] = Field(
        None,
        alias="fiscalDateEnding",
        description="Fiscal period end date"
    )

    # Update timestamp
    updated_from_date: Optional[datetime] = Field(
        None,
        alias="updatedFromDate",
        description="Last update timestamp"
    )

    @property
    def eps_surprise(self) -> Optional[float]:
        """Calculate EPS surprise.

        Returns:
            EPS surprise (actual - estimated) or None
        """
        if self.eps is not None and self.eps_estimated is not None:
            return self.eps - self.eps_estimated
        return None

    @property
    def eps_surprise_percent(self) -> Optional[float]:
        """Calculate EPS surprise percentage.

        Returns:
            EPS surprise percentage or None
        """
        if self.eps is not None and self.eps_estimated is not None and self.eps_estimated != 0:
            return ((self.eps - self.eps_estimated) / abs(self.eps_estimated)) * 100
        return None

    @property
    def revenue_surprise(self) -> Optional[float]:
        """Calculate revenue surprise.

        Returns:
            Revenue surprise (actual - estimated) or None
        """
        if self.revenue is not None and self.revenue_estimated is not None:
            return self.revenue - self.revenue_estimated
        return None
