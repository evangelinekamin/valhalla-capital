"""Pydantic models for trade execution results returned to Overseer."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TradeExecution(BaseModel):
    """Details of order execution."""

    ticker: str = Field(description="Stock ticker")
    action: Literal["BUY", "SELL"] = Field(description="Trade action")
    quantity: float = Field(ge=0, description="Number of shares")
    status: Literal[
        "FILLED", "PARTIAL", "REJECTED", "FAILED", "PENDING", "CANCELLED", "SUBMITTED"
    ] = Field(description="Execution status")
    filled_price: Optional[float] = Field(
        default=None, description="Average fill price"
    )
    commission: Optional[float] = Field(default=None, description="Commission paid")
    order_id: Optional[int] = Field(default=None, description="IBKR order ID")


class KellyResult(BaseModel):
    """Kelly Criterion calculation results."""

    kelly_fraction: float = Field(description="Full Kelly fraction")
    half_kelly_fraction: float = Field(description="Half-Kelly fraction (actual used)")
    position_size_usd: float = Field(
        ge=0.0, description="Position size in USD"
    )
    position_size_shares: float = Field(ge=0, description="Position size in shares")


class RiskCheckResult(BaseModel):
    """Individual risk check result."""

    name: str = Field(description="Risk check name")
    passed: bool = Field(description="Whether check passed")
    message: str = Field(description="Check result message")


class TradeResult(BaseModel):
    """Complete trade processing result returned to Overseer."""

    request_id: UUID = Field(description="Original request ID")
    processed_at: datetime = Field(description="Processing timestamp")
    approved: bool = Field(description="Whether trade was approved and executed")
    trade_result: Optional[TradeExecution] = Field(
        default=None, description="Execution details if executed"
    )
    risk_checks: list[RiskCheckResult] = Field(
        default_factory=list, description="All risk check results"
    )
    kelly_calculation: Optional[KellyResult] = Field(
        default=None, description="Position sizing calculation"
    )
    message: str = Field(description="Human-readable result message")

    model_config = {"frozen": True}
