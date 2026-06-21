from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TweetBase(BaseModel):
    """Base tweet model."""
    miniflux_id: int
    feed_id: Optional[int] = None
    tweet_id: Optional[str] = None
    username: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None


class TweetFilters(BaseModel):
    """Tweet filtering parameters."""
    classification: Optional[str] = Field(None, description="Filter by classification (CRITICAL/IMPORTANT/ROUTINE/SKIP)")
    username: Optional[str] = Field(None, description="Filter by username")
    sentiment: Optional[str] = Field(None, description="Filter by sentiment (bullish/bearish/neutral)")
    ticker: Optional[str] = Field(None, description="Filter by ticker symbol")
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum confidence score")
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip")


class TweetResponse(BaseModel):
    """Tweet response model with all fields."""
    id: int
    miniflux_id: int
    feed_id: Optional[int]
    tweet_id: Optional[str]
    username: Optional[str]
    title: Optional[str]
    content: Optional[str]
    url: Optional[str]
    published_at: Optional[datetime]

    # Pre-filter fields
    pre_filter_action: Optional[str]
    pre_filter_reason: Optional[str]

    # LLM triage fields
    classification: Optional[str]
    confidence: Optional[float]

    # Extraction fields
    tickers: Optional[List[str]]
    sentiment: Optional[str]

    # Processing metadata
    fetched_at: Optional[datetime]
    processed: bool
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class TweetListResponse(BaseModel):
    """List of tweets with pagination info."""
    tweets: List[TweetResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class ClassificationStats(BaseModel):
    """Classification breakdown statistics."""
    CRITICAL: int = 0
    IMPORTANT: int = 0
    ROUTINE: int = 0
    SKIP: int = 0


class SentimentStats(BaseModel):
    """Sentiment breakdown statistics."""
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0


class PreFilterStats(BaseModel):
    """Pre-filter effectiveness statistics."""
    total: int = 0
    skipped: int = 0
    accepted: int = 0
    triaged: int = 0
    skip_rate: float = 0.0


class StatsResponse(BaseModel):
    """Overall statistics response."""
    total_tweets: int
    processed_tweets: int
    unprocessed_tweets: int
    classification_breakdown: ClassificationStats
    sentiment_breakdown: SentimentStats
    pre_filter_stats: PreFilterStats
    top_tickers: List[Dict[str, Any]]
    top_users: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    database_connected: bool
    processing_active: bool = False
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    version: str = "1.0.0"
