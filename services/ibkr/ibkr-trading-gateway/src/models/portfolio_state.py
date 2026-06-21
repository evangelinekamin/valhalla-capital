"""Pydantic model for portfolio state shared with Overseer."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Position(BaseModel):
    """Individual position in portfolio."""

    ticker: str = Field(description="Stock ticker")
    quantity: int = Field(description="Number of shares")
    avg_cost: float = Field(description="Average cost basis")
    current_price: float = Field(description="Current market price")
    market_value: float = Field(description="Current market value")
    unrealized_pnl: float = Field(description="Unrealized profit/loss")
    unrealized_pnl_pct: float = Field(description="Unrealized P&L percentage")


class PortfolioState(BaseModel):
    """Current portfolio state for Overseer."""

    timestamp: datetime = Field(description="State timestamp")
    total_value: float = Field(description="Total portfolio value (Net Liquidation)")
    cash_balance: float = Field(description="Available cash")
    positions: list[Position] = Field(
        default_factory=list, description="Current positions"
    )
    daily_pnl: float = Field(default=0.0, description="Today's P&L in dollars")
    daily_pnl_pct: float = Field(default=0.0, description="Today's P&L percentage")

    @property
    def positions_dict(self) -> dict[str, Any]:
        """Convert positions to dict for JSON storage."""
        return {p.ticker: p.model_dump() for p in self.positions}

    @property
    def total_position_value(self) -> float:
        """Total value of all positions."""
        return sum(p.market_value for p in self.positions)

    @property
    def position_count(self) -> int:
        """Number of open positions."""
        return len(self.positions)

    model_config = {"frozen": True}
