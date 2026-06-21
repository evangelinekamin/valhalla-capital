"""Valuation models - DCF and enterprise value."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field

from .base import FMPBaseModel


class DCFValuation(FMPBaseModel):
    """Discounted cash flow valuation."""

    symbol: str = Field(..., description="Stock ticker symbol")
    valuation_date: date = Field(..., alias="date", description="Valuation date")
    dcf: float = Field(..., description="DCF value per share")
    stock_price: Optional[float] = Field(
        None,
        alias="Stock Price",
        description="Current stock price"
    )

    @property
    def discount_to_dcf(self) -> Optional[float]:
        """Calculate discount/premium to DCF value.

        Returns:
            Percentage discount (negative) or premium (positive) to DCF
        """
        if self.stock_price is None:
            return None
        return ((self.stock_price - self.dcf) / self.dcf) * 100

    @property
    def is_undervalued(self) -> Optional[bool]:
        """Check if stock is undervalued based on DCF.

        Returns:
            True if undervalued, False if overvalued, None if cannot determine
        """
        if self.stock_price is None:
            return None
        return self.stock_price < self.dcf


class EnterpriseValue(FMPBaseModel):
    """Enterprise value and related metrics."""

    symbol: str = Field(..., description="Stock ticker symbol")
    valuation_date: date = Field(..., alias="date", description="Date")

    # Stock metrics
    stock_price: Optional[float] = Field(
        None,
        alias="stockPrice",
        description="Stock price"
    )
    number_of_shares: Optional[float] = Field(
        None,
        alias="numberOfShares",
        description="Shares outstanding"
    )

    # Market cap
    market_capitalization: Optional[float] = Field(
        None,
        alias="marketCapitalization",
        description="Market capitalization"
    )

    # Debt and cash
    minus_cash_and_equivalents: Optional[float] = Field(
        None,
        alias="minusCashAndCashEquivalents",
        description="Cash and equivalents (subtracted)"
    )
    add_total_debt: Optional[float] = Field(
        None,
        alias="addTotalDebt",
        description="Total debt (added)"
    )

    # Enterprise value
    enterprise_value: Optional[float] = Field(
        None,
        alias="enterpriseValue",
        description="Enterprise value"
    )

    @property
    def net_debt(self) -> Optional[float]:
        """Calculate net debt.

        Returns:
            Net debt (total debt - cash)
        """
        if self.add_total_debt is None or self.minus_cash_and_equivalents is None:
            return None
        return self.add_total_debt - self.minus_cash_and_equivalents
