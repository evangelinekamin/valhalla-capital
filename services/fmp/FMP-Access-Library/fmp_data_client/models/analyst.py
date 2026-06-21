"""Analyst data models - estimates, price targets, grades."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import Field

from .base import FMPBaseModel


class AnalystEstimate(FMPBaseModel):
    """Analyst earnings and revenue estimates."""

    symbol: str = Field(..., description="Stock ticker symbol")
    estimate_date: date = Field(..., alias="date", description="Estimate date")

    # EPS estimates
    estimated_eps_avg: Optional[float] = Field(
        None,
        alias="estimatedEpsAvg",
        description="Average estimated EPS"
    )
    estimated_eps_high: Optional[float] = Field(
        None,
        alias="estimatedEpsHigh",
        description="High estimated EPS"
    )
    estimated_eps_low: Optional[float] = Field(
        None,
        alias="estimatedEpsLow",
        description="Low estimated EPS"
    )
    number_analyst_estimated_eps: Optional[int] = Field(
        None,
        alias="numberAnalystEstimatedEps",
        description="Number of analysts providing EPS estimates"
    )

    # Revenue estimates
    estimated_revenue_avg: Optional[float] = Field(
        None,
        alias="estimatedRevenueAvg",
        description="Average estimated revenue"
    )
    estimated_revenue_high: Optional[float] = Field(
        None,
        alias="estimatedRevenueHigh",
        description="High estimated revenue"
    )
    estimated_revenue_low: Optional[float] = Field(
        None,
        alias="estimatedRevenueLow",
        description="Low estimated revenue"
    )
    number_analysts_estimated_revenue: Optional[int] = Field(
        None,
        alias="numberAnalystsEstimatedRevenue",
        description="Number of analysts providing revenue estimates"
    )


class PriceTarget(FMPBaseModel):
    """Individual analyst price target."""

    symbol: str = Field(..., description="Stock ticker symbol")
    published_date: date = Field(
        ...,
        alias="publishedDate",
        description="Publication date"
    )

    # Price target
    price_target: Optional[float] = Field(
        None,
        alias="priceTarget",
        description="Price target"
    )
    price_when_posted: Optional[float] = Field(
        None,
        alias="priceWhenPosted",
        description="Stock price when target was posted"
    )

    # Analyst info
    analyst_name: Optional[str] = Field(
        None,
        alias="analystName",
        description="Analyst name"
    )
    analyst_company: Optional[str] = Field(
        None,
        alias="analystCompany",
        description="Analyst firm"
    )

    # News info
    news_url: Optional[str] = Field(
        None,
        alias="newsURL",
        description="News article URL"
    )
    news_title: Optional[str] = Field(
        None,
        alias="newsTitle",
        description="News article title"
    )
    news_publisher: Optional[str] = Field(
        None,
        alias="newsPublisher",
        description="News publisher"
    )

    @property
    def upside_potential(self) -> Optional[float]:
        """Calculate upside potential from current price to target.

        Returns:
            Percentage upside to price target, or None if missing data
        """
        if self.price_target is None or self.price_when_posted is None:
            return None
        if self.price_when_posted == 0:
            return None
        return ((self.price_target - self.price_when_posted) / self.price_when_posted) * 100


class PriceTargetSummary(FMPBaseModel):
    """Aggregated price target summary."""

    symbol: str = Field(..., description="Stock ticker symbol")
    last_month: Optional[float] = Field(
        None,
        alias="lastMonth",
        description="Average price target from last month"
    )
    last_month_avg_price_target: Optional[float] = Field(
        None,
        alias="lastMonthAvgPriceTarget",
        description="Average price target from last month (alternative field)"
    )
    last_quarter: Optional[float] = Field(
        None,
        alias="lastQuarter",
        description="Average price target from last quarter"
    )
    last_quarter_avg_price_target: Optional[float] = Field(
        None,
        alias="lastQuarterAvgPriceTarget",
        description="Average price target from last quarter (alternative field)"
    )

    @property
    def current_avg(self) -> Optional[float]:
        """Get the most recent average price target.

        Returns:
            Most recent average price target
        """
        return self.last_month or self.last_month_avg_price_target


class AnalystGrade(FMPBaseModel):
    """Analyst upgrade/downgrade/initiation."""

    symbol: str = Field(..., description="Stock ticker symbol")
    published_date: datetime = Field(
        ...,
        alias="publishedDate",
        description="Publication date"
    )

    # Grade info
    grading_company: str = Field(
        ...,
        alias="gradingCompany",
        description="Analyst firm"
    )
    new_grade: Optional[str] = Field(
        None,
        alias="newGrade",
        description="New rating"
    )
    previous_grade: Optional[str] = Field(
        None,
        alias="previousGrade",
        description="Previous rating"
    )

    # Price target
    price_when_posted: Optional[float] = Field(
        None,
        alias="priceWhenPosted",
        description="Stock price when posted"
    )

    # Action
    action: Optional[str] = Field(
        None,
        description="Action type (upgrade, downgrade, init, reiterate)"
    )

    @property
    def is_upgrade(self) -> bool:
        """Check if this is an upgrade.

        Returns:
            True if upgrade
        """
        return self.action and self.action.lower() == "upgrade"

    @property
    def is_downgrade(self) -> bool:
        """Check if this is a downgrade.

        Returns:
            True if downgrade
        """
        return self.action and self.action.lower() == "downgrade"

    @property
    def is_initiation(self) -> bool:
        """Check if this is a new coverage initiation.

        Returns:
            True if initiation
        """
        return self.action and self.action.lower() in ("init", "initiated")
