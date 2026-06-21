"""
Pydantic models for Yellowbrick pitch data.

These models match the schema defined in schema.sql and provide:
- Type validation
- Data transformation (e.g., ticker uppercase)
- Immutability (frozen models)
- Sensible defaults

IMPORTANT: All models are immutable. Use model_copy() to create modified copies.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class FeedType(str, Enum):
    """Valid feed types for Yellowbrick pitches."""

    BIG_MONEY = "big_money"
    ELITE = "elite"


class ScrapeStatus(str, Enum):
    """Status of a scrape operation."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    PENDING = "PENDING"


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class Pitch(BaseModel):
    """
    Pydantic model representing a Yellowbrick pitch.

    Maps to the yellowbrick_pitches table in schema.sql.
    All instances are immutable (frozen=True).
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    # Core identification (required)
    ticker: str = Field(..., min_length=1, max_length=10)
    feed_type: str = Field(...)
    pitch_id: str = Field(...)
    author: str = Field(...)

    # Pitch details (optional)
    author_type: str | None = Field(default=None)
    pitch_date: datetime | None = Field(default=None)
    pitch_type: str | None = Field(default=None)

    # Content (optional)
    title: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    full_content: str | None = Field(default=None)
    reasoning: str | None = Field(default=None)
    target_price: Decimal | None = Field(default=None)
    time_horizon: str | None = Field(default=None)

    # Metadata (optional)
    source_url: str | None = Field(default=None)
    filing_type: str | None = Field(default=None)
    position_size: str | None = Field(default=None)
    metadata: dict[str, Any] | None = Field(default=None)

    # Tracking (with defaults)
    first_seen_at: datetime = Field(default_factory=_utc_now)
    last_updated_at: datetime = Field(default_factory=_utc_now)
    is_active: bool = Field(default=True)

    @field_validator("ticker", mode="before")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        """Convert ticker to uppercase and validate."""
        if value is None:
            raise ValueError("ticker cannot be None")

        ticker = str(value).strip().upper()

        if not ticker:
            raise ValueError("ticker cannot be empty")

        if len(ticker) > 10:
            raise ValueError("ticker cannot exceed 10 characters")

        return ticker

    @field_validator("feed_type", mode="before")
    @classmethod
    def validate_feed_type(cls, value: str) -> str:
        """Validate feed_type is one of allowed values."""
        if value is None:
            raise ValueError("feed_type cannot be None")

        feed_type = str(value).strip().lower()
        valid_types = {ft.value for ft in FeedType}

        if feed_type not in valid_types:
            raise ValueError(
                f"feed_type must be one of {valid_types}, got '{feed_type}'"
            )

        return feed_type

    @field_validator("pitch_date", mode="before")
    @classmethod
    def validate_pitch_date(cls, value: datetime | str | None) -> datetime | None:
        """Parse pitch_date from string if needed."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            # Handle ISO format date strings
            date_str = value.strip()
            if not date_str:
                return None

            # Try ISO format with time
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

            # Try date-only format
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

            raise ValueError(f"Invalid date format: {date_str}")

        raise ValueError(f"pitch_date must be datetime or string, got {type(value)}")

    @field_validator("target_price", mode="before")
    @classmethod
    def validate_target_price(cls, value: Decimal | float | str | None) -> Decimal | None:
        """Convert target_price to Decimal."""
        if value is None:
            return None

        if isinstance(value, Decimal):
            return value

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        if isinstance(value, str):
            return Decimal(value)

        raise ValueError(f"target_price must be numeric, got {type(value)}")


class ScrapeLog(BaseModel):
    """
    Pydantic model for scrape operation logs.

    Maps to the yellowbrick_scrape_log table in schema.sql.
    All instances are immutable (frozen=True).
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    # Required fields
    feed_type: str = Field(...)
    status: str = Field(...)

    # Timestamps
    scrape_timestamp: datetime = Field(default_factory=_utc_now)

    # Results (with defaults)
    pitches_found: int = Field(default=0)
    pitches_new: int = Field(default=0)
    pitches_updated: int = Field(default=0)

    # Performance
    duration_seconds: Decimal | None = Field(default=None)

    # Error tracking
    error_message: str | None = Field(default=None)

    @field_validator("feed_type", mode="before")
    @classmethod
    def validate_feed_type(cls, value: str) -> str:
        """Validate feed_type is one of allowed values."""
        if value is None:
            raise ValueError("feed_type cannot be None")

        feed_type = str(value).strip().lower()
        valid_types = {ft.value for ft in FeedType}

        if feed_type not in valid_types:
            raise ValueError(
                f"feed_type must be one of {valid_types}, got '{feed_type}'"
            )

        return feed_type

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Validate status is one of allowed values."""
        if value is None:
            raise ValueError("status cannot be None")

        status = str(value).strip().upper()
        valid_statuses = {s.value for s in ScrapeStatus}

        if status not in valid_statuses:
            raise ValueError(
                f"status must be one of {valid_statuses}, got '{status}'"
            )

        return status
