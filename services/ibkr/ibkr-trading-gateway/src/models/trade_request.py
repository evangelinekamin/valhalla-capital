"""Pydantic models for incoming trade requests from Overseer."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AnalysisData(BaseModel):
    """Claude's analysis data for position sizing."""

    win_probability: float = Field(
        ge=0.0, le=1.0, description="Probability of profitable trade (0-1)"
    )
    expected_gain_pct: float = Field(
        gt=0.0, description="Expected gain percentage (positive)"
    )
    expected_loss_pct: float = Field(
        lt=0.0, description="Expected loss percentage (negative)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in analysis (0-1)",
    )

    model_config = {"frozen": True}


class TradeRequest(BaseModel):
    """Trade request from Overseer Claude."""

    request_id: UUID = Field(description="Unique request identifier")
    timestamp: datetime = Field(description="Request timestamp")
    ticker: str = Field(
        min_length=1, max_length=10, description="Stock ticker symbol"
    )
    action: Literal["BUY", "SELL"] = Field(description="Trade action")
    analysis: AnalysisData = Field(description="Kelly calculation inputs")
    reasoning: str = Field(description="Trade rationale")
    quantity: Optional[float] = Field(
        default=None, gt=0, description="Requested quantity from Overseer"
    )
    kelly_fraction: Optional[float] = Field(
        default=None, ge=0, le=1, description="Kelly fraction from Overseer"
    )

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        """Ensure ticker is uppercase."""
        return v.upper().strip()

    model_config = {"frozen": True}
