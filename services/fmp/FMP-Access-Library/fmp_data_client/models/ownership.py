"""Ownership models - institutional holders, insider trades, holder classification."""

from datetime import date, datetime
from typing import Optional

from pydantic import Field

from .base import FMPBaseModel


class InstitutionalHolder(FMPBaseModel):
    """Institutional ownership position."""

    # Holder info
    cik: Optional[str] = Field(None, description="SEC CIK number")
    holder: str = Field(..., description="Institution name")

    # Position
    shares: int = Field(..., description="Number of shares held")
    date_reported: date = Field(
        ...,
        alias="dateReported",
        description="Report date"
    )

    # Change
    change: Optional[int] = Field(
        None,
        description="Change in shares from previous period"
    )
    change_percent: Optional[float] = Field(
        None,
        alias="changePercent",
        description="Percentage change in position"
    )

    # Value
    value: Optional[float] = Field(
        None,
        alias="marketValue",
        description="Market value of position"
    )

    # Weight
    weight_percent: Optional[float] = Field(
        None,
        alias="weightPercent",
        description="Percentage of institution's portfolio"
    )
    percent_held: Optional[float] = Field(
        None,
        alias="percentHeld",
        description="Percentage of outstanding shares held"
    )

    @property
    def is_increased_position(self) -> Optional[bool]:
        """Check if position was increased.

        Returns:
            True if increased, False if decreased, None if unknown
        """
        if self.change is None:
            return None
        return self.change > 0

    @property
    def is_new_position(self) -> bool:
        """Check if this is a new position.

        Returns:
            True if new position (no previous shares)
        """
        # If change equals shares, this is a new position
        return self.change is not None and self.change == self.shares

    @property
    def position_change_type(self) -> Optional[str]:
        """Get the type of position change.

        Returns:
            "increased", "decreased", "new", or None if unknown
        """
        if self.change is None:
            return None
        if self.is_new_position:
            return "new"
        return "increased" if self.change > 0 else "decreased"


class InsiderTrade(FMPBaseModel):
    """Insider trading transaction."""

    # Filing info
    filing_date: date = Field(
        ...,
        alias="filingDate",
        description="SEC filing date"
    )
    transaction_date: date = Field(
        ...,
        alias="transactionDate",
        description="Transaction date"
    )

    # Insider info
    reporting_cik: Optional[str] = Field(
        None,
        alias="reportingCik",
        description="Insider CIK"
    )
    reporting_name: str = Field(
        ...,
        alias="reportingName",
        description="Insider name"
    )
    type_of_owner: Optional[str] = Field(
        None,
        alias="typeOfOwner",
        description="Owner type (director, officer, 10% owner, etc.)"
    )

    # Security info
    security_name: str = Field(
        ...,
        alias="securityName",
        description="Security name"
    )
    symbol: str = Field(..., description="Stock ticker symbol")

    # Transaction details
    transaction_type: str = Field(
        ...,
        alias="transactionType",
        description="Transaction type (P=Purchase, S=Sale, etc.)"
    )
    acquisition_or_disposition: Optional[str] = Field(
        None,
        alias="acquistionOrDisposition",
        description="A=Acquisition, D=Disposition"
    )

    # Shares and price
    securities_transacted: float = Field(
        ...,
        alias="securitiesTransacted",
        description="Number of shares"
    )
    price: Optional[float] = Field(None, description="Transaction price per share")

    # Value
    securities_owned: Optional[float] = Field(
        None,
        alias="securitiesOwned",
        description="Total shares owned after transaction"
    )

    # Link
    link: Optional[str] = Field(None, description="SEC filing link")

    @property
    def transaction_value(self) -> Optional[float]:
        """Calculate transaction value.

        Returns:
            Total value of transaction
        """
        if self.price is None:
            return None
        return self.securities_transacted * self.price

    @property
    def is_purchase(self) -> bool:
        """Check if this is a purchase.

        Returns:
            True if purchase
        """
        return self.transaction_type == "P" or (
            self.acquisition_or_disposition and
            self.acquisition_or_disposition.upper() == "A"
        )

    @property
    def is_sale(self) -> bool:
        """Check if this is a sale.

        Returns:
            True if sale
        """
        return self.transaction_type == "S" or (
            self.acquisition_or_disposition and
            self.acquisition_or_disposition.upper() == "D"
        )


class HolderClassification(FMPBaseModel):
    """Classification and weighting for institutional holders.

    Used for institutional analysis to weight different types of holders
    based on their investing style and historical performance.
    """

    # Holder identification
    holder_name: str = Field(..., description="Institution name")
    cik: Optional[str] = Field(None, description="SEC CIK number")

    # Classification
    holder_type: str = Field(
        ...,
        description="Holder type (activist, index, value, growth, etc.)"
    )

    # Signal weight
    signal_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Signal weight for this holder (0.0-1.0)"
    )

    # Reputation
    reputation_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=10.0,
        description="Reputation score (0-10)"
    )

    # Notes
    notes: Optional[str] = Field(
        None,
        description="Additional notes about this holder"
    )

    @property
    def is_high_signal(self) -> bool:
        """Check if this is a high-signal holder.

        Returns:
            True if signal weight >= 0.7
        """
        return self.signal_weight >= 0.7

    @property
    def is_passive(self) -> bool:
        """Check if this is a passive holder.

        Returns:
            True if holder type indicates passive investing
        """
        return self.holder_type.lower() in ("index", "etf", "passive")
