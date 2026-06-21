"""Quote and after-market quote models."""

from datetime import datetime
from typing import Optional

from pydantic import Field

from .base import FMPBaseModel


class Quote(FMPBaseModel):
    """Real-time stock quote data."""

    symbol: str = Field(..., description="Stock ticker symbol")
    price: float = Field(..., description="Current price")
    volume: float = Field(..., description="Trading volume")

    # Price changes
    change: float = Field(..., description="Price change in dollars")
    change_percent: float = Field(
        ...,
        alias="changePercentage",
        description="Price change percentage"
    )

    # Day range
    day_high: float = Field(..., alias="dayHigh", description="Day high price")
    day_low: float = Field(..., alias="dayLow", description="Day low price")

    # Previous close
    previous_close: float = Field(
        ...,
        alias="previousClose",
        description="Previous closing price"
    )

    # Market cap
    market_cap: Optional[float] = Field(
        None,
        alias="marketCap",
        description="Market capitalization"
    )

    # 52-week range
    year_high: Optional[float] = Field(
        None,
        alias="yearHigh",
        description="52-week high"
    )
    year_low: Optional[float] = Field(
        None,
        alias="yearLow",
        description="52-week low"
    )

    # Trading metrics
    open: Optional[float] = Field(None, description="Opening price")
    avg_volume: Optional[int] = Field(
        None,
        alias="avgVolume",
        description="Average volume"
    )

    # Valuation metrics
    pe: Optional[float] = Field(None, description="P/E ratio")
    eps: Optional[float] = Field(None, description="Earnings per share")

    # Timestamp
    timestamp: Optional[int] = Field(
        None,
        description="Unix timestamp of quote"
    )

    # Exchange
    exchange: Optional[str] = Field(
        None,
        description="Exchange where stock is traded"
    )

    # Name
    name: Optional[str] = Field(None, description="Company name")

    @property
    def timestamp_dt(self) -> Optional[datetime]:
        """Get timestamp as datetime object.

        Returns:
            Datetime object if timestamp is set, else None
        """
        if self.timestamp:
            return datetime.fromtimestamp(self.timestamp)
        return None

    @property
    def is_positive_change(self) -> bool:
        """Check if price change is positive.

        Returns:
            True if change is positive, else False
        """
        return self.change >= 0


class AftermarketQuote(FMPBaseModel):
    """After-market quote data (bid/ask spread)."""

    symbol: str = Field(..., description="Stock ticker symbol")

    # Bid
    bid_size: Optional[int] = Field(
        None,
        alias="bidSize",
        description="Bid size"
    )
    bid_price: Optional[float] = Field(
        None,
        alias="bidPrice",
        description="Bid price"
    )

    # Ask
    ask_size: Optional[int] = Field(
        None,
        alias="askSize",
        description="Ask size"
    )
    ask_price: Optional[float] = Field(
        None,
        alias="askPrice",
        description="Ask price"
    )

    # Volume
    volume: Optional[int] = Field(None, description="Trading volume")

    # Timestamp
    timestamp: Optional[int] = Field(
        None,
        description="Unix timestamp (milliseconds)"
    )

    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread.

        Returns:
            Spread or None if data unavailable
        """
        if self.bid_price is not None and self.ask_price is not None:
            return self.ask_price - self.bid_price
        return None
