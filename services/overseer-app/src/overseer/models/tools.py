from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallRecord(BaseModel):
    id: int | None = None
    cycle_log_id: int | None = None
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int | None = None
    error: str | None = None


class TwitterQueryInput(BaseModel):
    limit: int = 50
    since: str | None = None


class NewsQueryInput(BaseModel):
    include_acknowledged: bool = False


class SubstackQueryInput(BaseModel):
    limit: int = 20


class YellowbrickQueryInput(BaseModel):
    limit: int = 20
    feed_type: str | None = None


class OpenInsiderQueryInput(BaseModel):
    min_insider_count: int = 3
    limit: int = 20


class FMPDataInput(BaseModel):
    symbol: str
    include_quote: bool = True
    include_fundamentals: bool = True
    include_profile: bool = False


class MemorySearchInput(BaseModel):
    query: str
    top_k: int = 5
    event_type: str | None = None
    tickers: list[str] | None = None


class LogObservationInput(BaseModel):
    event_type: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.5


class ProposeTradeInput(BaseModel):
    ticker: str
    action: Literal["buy", "sell"]
    win_probability: float
    expected_gain_pct: float
    expected_loss_pct: float
    confidence: float
    reasoning: str
    falsification_criteria: list[str] = Field(default_factory=list)
    quantity_override: int | None = Field(
        default=None,
        description="Exact number of shares to trade. If omitted, Kelly sizing determines quantity.",
    )
    thesis_action: Literal[
        "close", "invalidate", "reverse", "trim", "add", "maintain"
    ] | None = Field(
        default=None,
        description=(
            "Only consulted when the trade CONFLICTS with an active thesis "
            "(LONG thesis + sell, or SHORT thesis + buy). For aligning trades "
            "(LONG thesis + buy, or SHORT thesis + sell) leave this null — "
            "the field is ignored. Conflict-resolution values: "
            "'close' (target hit — exit cleanly, thesis succeeded), "
            "'invalidate' (thesis broken by new evidence — exit), "
            "'reverse' (now believe opposite direction), "
            "'trim' (concentration/risk management, thesis still valid — for "
            "PARTIAL sells only; if you sell the whole position the thesis "
            "is auto-closed regardless of label). "
            "'add'/'maintain' are no-op labels for aligning trades; if you "
            "pass them on a conflicting trade the proposal is rejected."
        ),
    )
    thesis_reasoning: str | None = Field(
        default=None,
        description=(
            "REQUIRED when thesis_action is a conflict-resolution value "
            "(close/invalidate/reverse/trim) and the trade conflicts with the "
            "active thesis. Min 30 chars. Recorded in thesis_tracker.update_log."
        ),
    )

    @field_validator("quantity_override", mode="before")
    @classmethod
    def _floor_fractional_override(cls, v: Any) -> Any:
        # IBKR trades whole shares only. Coerce floats to floor-int so the
        # LLM can pass 2.5 without crashing pydantic's int_from_float check.
        if isinstance(v, float):
            return int(v)
        return v


class CapabilityWishInput(BaseModel):
    category: str
    title: str
    description: str
    reasoning: str
    priority: str = "nice_to_have"


class DiscordMessageInput(BaseModel):
    content: str
    message_type: str = "info"  # info, alert, trade, report


class CompareToThesisInput(BaseModel):
    decision_id: int
    current_data: dict[str, Any] = Field(default_factory=dict)


class EarningsCalendarInput(BaseModel):
    symbol: str


class CheckSpendingInput(BaseModel):
    days: int = Field(default=1, ge=1, le=90, description="Number of days to report (1=today, 7=week, 30=month)")


class CreateThesisInput(BaseModel):
    ticker: str
    thesis_statement: str
    position_type: str = "LONG"
    conviction: str = "MEDIUM"
    pillars: list[dict[str, Any]] = Field(default_factory=list)
    catalysts: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    target_price: float | None = None
    stop_loss: float | None = None
    valuation_methodology: str | None = None
    entry_price: float | None = None


class UpdateThesisInput(BaseModel):
    thesis_id: int
    data_point: str = Field(description="What new data prompted this update")
    thesis_impact: str = Field(description="How the data affects the thesis: CONFIRMS, WEAKENS, NEUTRALIZES")
    action: str = Field(default="MAINTAIN", description="INCREASE, MAINTAIN, DECREASE, EXIT")
    conviction_change: str | None = Field(default=None, description="New conviction level: LOW, MEDIUM, HIGH")
    pillar_updates: list[dict[str, Any]] | None = None
    new_catalysts: list[dict[str, Any]] | None = None
    new_risks: list[dict[str, Any]] | None = None
    target_price: float | None = None
    stop_loss: float | None = None


class CloseThesisInput(BaseModel):
    thesis_id: int
    reason: str
    outcome: str = Field(default="exited", description="exited, invalidated, or confirmed")


class GetThesesInput(BaseModel):
    ticker: str | None = None


class ResearchCompanyInput(BaseModel):
    ticker: str = Field(description="Ticker symbol, e.g. 'AAPL'.")
    source_type: Literal[
        "10-K", "10-Q", "8-K", "earnings_transcript", "DEF 14A"
    ] = Field(
        description=(
            "Which document to fetch. '10-K' = annual filing, '10-Q' = quarterly, "
            "'8-K' = material event, 'DEF 14A' = proxy statement, "
            "'earnings_transcript' = earnings call transcript text."
        ),
    )
    focus: str = Field(
        min_length=10,
        description=(
            "What you want to learn from this document — e.g. 'guidance change', "
            "'segment margins', 'capex trajectory', 'going-concern language'. "
            "Drives the worker's emphasis when summarizing."
        ),
    )
    period: str | None = Field(
        default=None,
        description=(
            "Most recent if null. Format: 'YYYY' for 10-K, 'YYYY-Q[1-4]' for "
            "10-Q/transcript, 'YYYY-MM-DD' for 8-K."
        ),
    )
