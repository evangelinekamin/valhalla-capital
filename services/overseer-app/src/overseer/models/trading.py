from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TradeAnalysis(BaseModel):
    win_probability: float
    expected_gain_pct: float
    expected_loss_pct: float
    confidence: float


class TradeRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ticker: str
    action: str  # buy, sell, short, cover
    analysis: TradeAnalysis
    reasoning: str
    quantity: float | None = None
    kelly_fraction: float | None = None


class TradeResult(BaseModel):
    request_id: UUID
    status: str  # accepted, rejected, filled, failed
    order_id: str | None = None
    quantity: float | None = None
    filled_quantity: float | None = None
    fill_price: float | None = None
    filled_at: datetime | None = None
    commission: float | None = None
    rejection_reason: str | None = None


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    price_source: str | None = None  # "ibkr", "fmp"


class PortfolioState(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_value: float = 0.0
    cash: float = 0.0
    cash_balance: float | None = None
    positions: list[Position] = Field(default_factory=list)
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    data_age_seconds: float | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.cash_balance is not None and self.cash == 0.0:
            object.__setattr__(self, "cash", self.cash_balance)


class KellySizing(BaseModel):
    # Trade size (the delta to reach target_weight)
    shares: float
    position_value: float

    # Kelly's preferred portfolio weight (capped by fresh_buy_cap), and
    # the existing weight Kelly is sizing against. Together these tell the
    # caller "I want this much exposure, you already have this much, so
    # buy the difference." Eliminates the buy-then-trim pattern where the
    # caller sized blind to existing concentration.
    target_weight: float = 0.0
    target_value: float = 0.0
    existing_weight: float = 0.0
    existing_value: float = 0.0
    delta_value: float = 0.0

    # Raw Kelly outputs (uncapped) — kept for transparency
    kelly_fraction: float
    half_kelly_fraction: float
    commission_round_trip: float
    commission_drag_pct: float
    rejection_reason: str | None = None


class RiskCheck(BaseModel):
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)
