"""
SQLAlchemy ORM models for the Twitter monitoring system.

This module defines the database schema for storing tweets with:
- Core tweet data (content, metadata)
- Pre-filter results (action, reason)
- LLM triage results (classification, confidence)
- Extraction results (tickers, sentiment)
- Processing metadata (fetched_at, processed, processed_at)

Database: PostgreSQL with ARRAY support
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    Index,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.types import TypeDecorator, TEXT


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class ArrayType(TypeDecorator):
    """
    Platform-independent array type.

    Uses PostgreSQL ARRAY when available, falls back to JSON-encoded
    TEXT for SQLite testing.
    """

    impl = TEXT
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_ARRAY(Text))
        return dialect.type_descriptor(TEXT())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        # For SQLite, serialize as JSON
        import json
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        # For SQLite, deserialize from JSON
        import json
        if isinstance(value, str):
            return json.loads(value)
        return value


class Tweet(Base):
    """
    ORM model for tweets table.

    Stores tweets fetched from Miniflux with classification and extraction data.

    Attributes:
        id: Auto-incrementing primary key
        miniflux_id: Unique ID from Miniflux (required)
        feed_id: Miniflux feed ID
        tweet_id: Twitter/X status ID extracted from URL
        username: Twitter username
        title: Tweet title from RSS
        content: Full tweet content/HTML
        url: Original tweet URL
        published_at: When the tweet was published

        pre_filter_action: Result of pre-filter (skip, triage, accept)
        pre_filter_reason: Reason for pre-filter decision

        classification: LLM classification (CRITICAL, IMPORTANT, ROUTINE, SKIP)
        confidence: LLM confidence score (0.0 - 1.0)

        tickers: List of ticker symbols mentioned (PostgreSQL ARRAY)
        sentiment: Overall sentiment (bullish, bearish, neutral)

        fetched_at: When the tweet was fetched (auto-set)
        processed: Whether the tweet has been processed
        processed_at: When the tweet was processed
    """

    __tablename__ = "tweets"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core tweet data
    miniflux_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False
    )
    feed_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tweet_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Pre-filter fields
    pre_filter_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pre_filter_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # LLM triage fields
    classification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Extraction fields
    tickers: Mapped[Optional[List[str]]] = mapped_column(
        ArrayType, nullable=True
    )
    sentiment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Processing metadata
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc)
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Table-level indexes (for PostgreSQL)
    __table_args__ = (
        Index("ix_tweets_username", "username"),
        Index("ix_tweets_classification", "classification"),
        Index("ix_tweets_sentiment", "sentiment"),
        # GIN index for tickers array - PostgreSQL only
        # This is created conditionally in create_tables()
    )

    def __repr__(self) -> str:
        return (
            f"<Tweet(id={self.id}, miniflux_id={self.miniflux_id}, "
            f"username={self.username}, classification={self.classification})>"
        )

    def to_dict(self) -> dict:
        """Convert tweet to dictionary representation."""
        return {
            "id": self.id,
            "miniflux_id": self.miniflux_id,
            "feed_id": self.feed_id,
            "tweet_id": self.tweet_id,
            "username": self.username,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "pre_filter_action": self.pre_filter_action,
            "pre_filter_reason": self.pre_filter_reason,
            "tier": self.tier,
            "classification": self.classification,
            "confidence": self.confidence,
            "tickers": self.tickers,
            "sentiment": self.sentiment,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "processed": self.processed,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


# Event listener to set fetched_at before insert
@event.listens_for(Tweet, "before_insert")
def set_fetched_at(mapper, connection, target):
    """Set fetched_at timestamp before insert if not already set."""
    if target.fetched_at is None:
        target.fetched_at = datetime.now(timezone.utc)


def create_gin_index(engine) -> None:
    """
    Create GIN index for tickers array (PostgreSQL only).

    GIN (Generalized Inverted Index) provides efficient queries for
    array containment operations like 'AAPL' = ANY(tickers).

    Args:
        engine: SQLAlchemy engine connected to PostgreSQL
    """
    if engine.dialect.name != "postgresql":
        return

    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tweets_tickers_gin
            ON tweets USING GIN (tickers)
        """))
        conn.commit()
