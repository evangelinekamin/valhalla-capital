"""Company profile and executive models."""

from datetime import date
from typing import List, Optional

from pydantic import Field, HttpUrl

from .base import FMPBaseModel


class Executive(FMPBaseModel):
    """Executive officer information."""

    name: str = Field(..., description="Executive name")
    title: str = Field(..., description="Job title")
    pay: Optional[float] = Field(None, description="Total compensation")
    currency_pay: Optional[str] = Field(
        None,
        alias="currencyPay",
        description="Currency of compensation"
    )
    gender: Optional[str] = Field(None, description="Gender")
    year_born: Optional[int] = Field(
        None,
        alias="yearBorn",
        description="Birth year"
    )
    title_since: Optional[int] = Field(
        None,
        alias="titleSince",
        description="Year started in current role"
    )


class CompanyProfile(FMPBaseModel):
    """Company profile with detailed information."""

    # Basic info
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., alias="companyName", description="Company name")
    price: Optional[float] = Field(None, description="Current stock price")

    # Company classification
    sector: Optional[str] = Field(None, description="Business sector")
    industry: Optional[str] = Field(None, description="Industry")

    # Description
    description: Optional[str] = Field(
        None,
        description="Company description"
    )

    # Leadership
    ceo: Optional[str] = Field(None, description="CEO name")

    # Size metrics
    employees: Optional[int] = Field(
        None,
        alias="fullTimeEmployees",
        description="Number of full-time employees"
    )

    # Contact info
    website: Optional[str] = Field(None, description="Company website URL")
    phone: Optional[str] = Field(None, description="Phone number")
    address: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    zip: Optional[str] = Field(None, description="Zip code")
    country: Optional[str] = Field(None, description="Country")

    # Financial info
    market_cap: Optional[float] = Field(
        None,
        alias="marketCap",
        description="Market capitalization"
    )

    # IPO
    ipo_date: Optional[date] = Field(
        None,
        alias="ipoDate",
        description="IPO date"
    )

    # Exchange info
    exchange: Optional[str] = Field(
        None,
        alias="exchange",
        description="Stock exchange"
    )
    currency: Optional[str] = Field(None, description="Trading currency")

    # Image
    image: Optional[str] = Field(None, description="Company logo URL")

    # Additional info
    is_etf: Optional[bool] = Field(
        None,
        alias="isEtf",
        description="Whether this is an ETF"
    )
    is_actively_trading: Optional[bool] = Field(
        None,
        alias="isActivelyTrading",
        description="Whether actively trading"
    )
    is_adr: Optional[bool] = Field(
        None,
        alias="isAdr",
        description="Whether this is an ADR"
    )
    is_fund: Optional[bool] = Field(
        None,
        alias="isFund",
        description="Whether this is a fund"
    )

    # Beta and volatility
    beta: Optional[float] = Field(None, description="Stock beta")
    vol_avg: Optional[int] = Field(
        None,
        alias="averageVolume",
        description="Average volume"
    )

    # Price range
    last_div: Optional[float] = Field(
        None,
        alias="lastDividend",
        description="Last dividend amount"
    )
    range: Optional[str] = Field(None, description="52-week price range")
    changes: Optional[float] = Field(None, description="Price change")

    # DCG
    dcf: Optional[float] = Field(None, description="Discounted cash flow value")
    dcf_diff: Optional[float] = Field(
        None,
        alias="dcfDiff",
        description="Difference between price and DCF"
    )

    # CIK for SEC filings
    cik: Optional[str] = Field(None, description="SEC CIK number")
    cusip: Optional[str] = Field(None, description="CUSIP identifier")
    isin: Optional[str] = Field(None, description="ISIN identifier")

    @property
    def full_address(self) -> Optional[str]:
        """Get formatted full address.

        Returns:
            Formatted address string or None
        """
        parts = [
            self.address,
            self.city,
            self.state,
            self.zip,
            self.country,
        ]
        parts = [p for p in parts if p]
        return ", ".join(parts) if parts else None

    @property
    def market_cap_formatted(self) -> Optional[str]:
        """Get human-readable market cap.

        Returns:
            Formatted market cap string (e.g., "$1.2T")
        """
        if not self.market_cap:
            return None

        mc = self.market_cap
        if mc >= 1_000_000_000_000:
            return f"${mc / 1_000_000_000_000:.2f}T"
        elif mc >= 1_000_000_000:
            return f"${mc / 1_000_000_000:.2f}B"
        elif mc >= 1_000_000:
            return f"${mc / 1_000_000:.2f}M"
        else:
            return f"${mc:,.0f}"
