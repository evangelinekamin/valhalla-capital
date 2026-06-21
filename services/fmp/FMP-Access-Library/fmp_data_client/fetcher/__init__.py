"""API fetcher modules for FMP endpoints."""

from .base import DataFetcher, FMPAPIError, RateLimiter, RateLimitError, TierAccessError
from .endpoints import BASE_URL, TIER_REQUIREMENTS, Endpoint, get_endpoint_url
from .specialized import SpecializedFetcher
from .tier import (
    can_access_endpoint,
    get_accessible_endpoints,
    get_rate_limit_for_tier,
    get_required_tier,
)

__all__ = [
    # Base
    "DataFetcher",
    "RateLimiter",
    "FMPAPIError",
    "RateLimitError",
    "TierAccessError",
    # Endpoints
    "Endpoint",
    "BASE_URL",
    "TIER_REQUIREMENTS",
    "get_endpoint_url",
    # Tier
    "can_access_endpoint",
    "get_accessible_endpoints",
    "get_required_tier",
    "get_rate_limit_for_tier",
    # Specialized
    "SpecializedFetcher",
]
