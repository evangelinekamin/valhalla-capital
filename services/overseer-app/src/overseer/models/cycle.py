from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CycleConfig(BaseModel):
    cycle_type: str
    model: str
    max_cost_cents: float
    cron_expression: str
    market_hours_only: bool = True
    system_prompt_addendum: str = ""


class CycleLog(BaseModel):
    id: int | None = None
    cycle_type: str
    model: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    tokens_used: dict[str, int] = Field(default_factory=dict)
    tools_called: list[dict[str, Any]] = Field(default_factory=list)
    cost_cents: float = 0.0
    error: str | None = None
    summary: str | None = None


class DecisionEntry(BaseModel):
    id: int | None = None
    cycle_log_id: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    decision_type: str
    summary: str
    reasoning: str
    tickers: list[str] = Field(default_factory=list)
    confidence: float | None = None
    falsification_criteria: list[dict[str, Any]] = Field(default_factory=list)
    outcome: str = "pending"
    outcome_details: dict[str, Any] | None = None
    reviewed_at: datetime | None = None


class CapabilityWish(BaseModel):
    id: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    category: str
    title: str
    description: str
    reasoning: str
    priority: str = "nice_to_have"
    frequency: int = 1
    last_wished_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "open"
    human_response: str | None = None
    resolved_at: datetime | None = None


CYCLE_CONFIGS: dict[str, CycleConfig] = {
    # NOTE: APScheduler day_of_week uses 0=Monday, 6=Sunday
    # (differs from standard cron where 0=Sunday)
    # Models routed through OpenRouter (non-claude- prefix -> openrouter_client.py)
    "quick_check": CycleConfig(
        cycle_type="quick_check",
        model="deepseek/deepseek-v3.2",
        max_cost_cents=50.0,
        cron_expression="*/30 * * * 0-4",
        market_hours_only=True,
    ),
    "data_synthesis": CycleConfig(
        cycle_type="data_synthesis",
        model="deepseek/deepseek-v3.2",
        max_cost_cents=500.0,
        cron_expression="0 */4 * * 0-4",
        market_hours_only=True,
    ),
    "deep_analysis": CycleConfig(
        cycle_type="deep_analysis",
        model="qwen/qwen-plus",
        max_cost_cents=1000.0,
        cron_expression="0 14 * * 0-4",
        market_hours_only=True,
    ),
    "daily_review": CycleConfig(
        cycle_type="daily_review",
        model="x-ai/grok-4.1-fast",
        max_cost_cents=2000.0,
        cron_expression="0 8 * * 0-4",
        market_hours_only=False,
    ),
    "weekly_review": CycleConfig(
        cycle_type="weekly_review",
        model="x-ai/grok-4.1-fast",
        max_cost_cents=5000.0,
        cron_expression="0 10 * * 6",
        market_hours_only=False,
    ),
    "monthly_review": CycleConfig(
        cycle_type="monthly_review",
        model="x-ai/grok-4.1-fast",
        max_cost_cents=5000.0,
        cron_expression="0 10 1 * *",
        market_hours_only=False,
    ),
}
