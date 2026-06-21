"""Pydantic models for OpenInsider data."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def classify_insider_type(title: str) -> str:
    """Classify insider type from their reported title.

    Args:
        title: The insider's reported title (e.g., "CEO", "10% Owner", "Director").

    Returns:
        One of: "executive", "fund", "director", "other".
    """
    title_lower = title.lower() if title else ""

    if any(role in title_lower for role in ["ceo", "cfo", "president", "chief", "officer"]):
        return "executive"
    if any(role in title_lower for role in ["fund", "10% owner", "owner"]):
        return "fund"
    if "director" in title_lower:
        return "director"

    return "other"


class ClusterBuy(BaseModel):
    """Represents an insider cluster buy event."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    insider_count: int
    filing_date: datetime
    trade_date: date
    trade_type: str
    avg_price: Optional[Decimal] = None
    total_qty: Optional[int] = None
    total_owned: Optional[int] = None
    ownership_change_pct: Optional[str] = None
    total_value: Optional[int] = None
    transaction_code: Optional[str] = None
    perf_1d: Optional[Decimal] = None
    perf_1w: Optional[Decimal] = None
    perf_1m: Optional[Decimal] = None
    perf_6m: Optional[Decimal] = None
    source_url: Optional[str] = None
    first_seen_at: datetime = Field(default_factory=_utcnow)
    last_updated_at: datetime = Field(default_factory=_utcnow)
    is_active: bool = True

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        """Convert ticker to uppercase."""
        return v.upper().strip()

    @field_validator("insider_count")
    @classmethod
    def validate_insider_count(cls, v: int) -> int:
        """Validate insider count is positive."""
        if v < 1:
            raise ValueError("Insider count must be at least 1")
        return v


class InsiderTransaction(BaseModel):
    """Represents an individual insider transaction (Phase 2)."""

    model_config = ConfigDict(frozen=True)

    cluster_buy_id: Optional[int] = None
    ticker: str
    insider_name: str
    insider_title: Optional[str] = None
    insider_type: str
    trade_date: date
    trade_type: str
    price: Optional[Decimal] = None
    qty: Optional[int] = None
    owned_after: Optional[int] = None
    ownership_change_pct: Optional[Decimal] = None
    value: Optional[int] = None
    form_type: Optional[str] = None
    sec_link: Optional[str] = None
    scraped_at: datetime = Field(default_factory=_utcnow)

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        """Convert ticker to uppercase."""
        return v.upper().strip()

    @field_validator("insider_type")
    @classmethod
    def classify_insider(cls, v: str, info) -> str:
        """Auto-classify insider type from title if not provided."""
        if v and v.lower() != "unknown":
            return v.lower()
        title = info.data.get("insider_title", "")
        return classify_insider_type(title)


class ScrapeLog(BaseModel):
    """Represents a scrape execution log entry."""

    model_config = ConfigDict(frozen=True)

    scrape_timestamp: datetime = Field(default_factory=_utcnow)
    scrape_type: str
    records_found: int = 0
    records_new: int = 0
    records_updated: int = 0
    duration_seconds: Optional[Decimal] = None
    status: str
    error_message: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of allowed values."""
        allowed = {"SUCCESS", "PARTIAL", "FAILED"}
        if v.upper() not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return v.upper()
