"""API request and response models for REST server."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = Field(True, description="Operation success status")
    message: Optional[str] = Field(None, description="Success message")


class QuoteResponse(BaseModel):
    """Quote data response."""

    symbol: str
    price: float
    change: float
    change_percent: float
    volume: float
    day_high: float
    day_low: float
    previous_close: float
    market_cap: Optional[float] = None
    timestamp: Optional[int] = None


class ProfileResponse(BaseModel):
    """Company profile response."""

    symbol: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    ceo: Optional[str] = None
    employees: Optional[int] = None
    website: Optional[str] = None
    country: Optional[str] = None
    market_cap: Optional[float] = None
    exchange: Optional[str] = None


class CacheStatusResponse(BaseModel):
    """Cache status response."""

    enabled: bool = Field(..., description="Whether cache is enabled")
    total_entries: Optional[int] = Field(None, description="Total cached entries")
    hit_rate: Optional[float] = Field(None, description="Cache hit rate")
    stats: Optional[Dict[str, Any]] = Field(None, description="Detailed cache statistics")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Health status (healthy/degraded/unhealthy)")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current timestamp")
    components: Dict[str, str] = Field(
        default_factory=dict, description="Component health status"
    )


class RateLimitInfo(BaseModel):
    """Rate limit information."""

    limit: int = Field(..., description="Rate limit (requests per minute)")
    remaining: int = Field(..., description="Remaining requests in current window")
    reset_at: Optional[str] = Field(None, description="When the limit resets")


class TickerDataResponse(BaseModel):
    """Comprehensive ticker data response."""

    symbol: str
    data: Dict[str, Any] = Field(..., description="Ticker data matching DataRequest")
    cached: bool = Field(False, description="Whether data was served from cache")
    fetched_at: Optional[str] = Field(None, description="When data was fetched")
