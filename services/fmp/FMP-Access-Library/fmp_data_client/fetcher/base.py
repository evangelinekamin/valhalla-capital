"""Base data fetcher with rate limiting and retry logic."""

import asyncio
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import FMPConfig, Tier
from .endpoints import BASE_URL, Endpoint, get_endpoint_url
from .tier import can_access_endpoint


class TierAccessError(Exception):
    """Raised when user tier is insufficient for endpoint."""

    pass


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    pass


class FMPAPIError(Exception):
    """Base exception for FMP API errors."""

    pass


class RateLimiter:
    """Token bucket rate limiter for API calls.

    Implements a token bucket algorithm to enforce rate limits.
    """

    def __init__(self, calls_per_minute: int):
        """Initialize rate limiter.

        Args:
            calls_per_minute: Maximum API calls per minute
        """
        self.calls_per_minute = calls_per_minute
        self.tokens = float(calls_per_minute)
        self.max_tokens = float(calls_per_minute)
        self.refill_rate = calls_per_minute / 60.0  # Tokens per second
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token to make an API call.

        Blocks until a token is available.
        """
        async with self._lock:
            while True:
                now = time.time()
                elapsed = now - self.last_refill

                # Refill tokens based on elapsed time
                self.tokens = min(
                    self.max_tokens,
                    self.tokens + (elapsed * self.refill_rate)
                )
                self.last_refill = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Calculate wait time for next token
                wait_time = (1.0 - self.tokens) / self.refill_rate
                await asyncio.sleep(wait_time)

    def get_status(self) -> Dict[str, Any]:
        """Get current rate limiter status.

        Returns:
            Dictionary with tokens remaining and refill rate
        """
        now = time.time()
        elapsed = now - self.last_refill
        current_tokens = min(
            self.max_tokens,
            self.tokens + (elapsed * self.refill_rate)
        )

        return {
            "tokens_remaining": current_tokens,
            "max_tokens": self.max_tokens,
            "calls_per_minute": self.calls_per_minute,
            "refill_rate_per_second": self.refill_rate,
        }


class DataFetcher:
    """Async HTTP client for FMP API with tier enforcement and rate limiting."""

    def __init__(self, config: FMPConfig):
        """Initialize data fetcher.

        Args:
            config: FMP configuration
        """
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiter = RateLimiter(config.get_rate_limit())

    async def __aenter__(self) -> "DataFetcher":
        """Enter async context manager."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        await self.close()

    async def start(self) -> None:
        """Initialize HTTP session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "FMP-Data-Client/0.1.0"}
            )

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            # Small delay to allow connection cleanup
            await asyncio.sleep(0.1)

    def _validate_tier_access(self, endpoint: Endpoint) -> None:
        """Validate user has access to endpoint.

        Args:
            endpoint: Endpoint to validate

        Raises:
            TierAccessError: If user tier is insufficient
        """
        if not can_access_endpoint(self.config.tier, endpoint):
            raise TierAccessError(
                f"Endpoint {endpoint.name} requires a higher tier. "
                f"Your tier: {self.config.tier.value}"
            )

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(
        self,
        endpoint: Endpoint,
        path_params: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Fetch data from FMP API endpoint.

        Args:
            endpoint: API endpoint to call
            path_params: Path parameters for URL formatting
            query_params: Query parameters

        Returns:
            JSON response data

        Raises:
            TierAccessError: If user tier insufficient
            RateLimitError: If rate limit exceeded
            FMPAPIError: If API returns error
        """
        # Ensure session is initialized
        if self.session is None or self.session.closed:
            await self.start()

        # Validate tier access
        self._validate_tier_access(endpoint)

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        # Build URL
        path_params = path_params or {}
        query_params = query_params or {}

        endpoint_path = get_endpoint_url(endpoint, **path_params)
        url = f"{BASE_URL}{endpoint_path}"

        # Add API key to query params
        query_params["apikey"] = self.config.api_key

        # Add query string
        if query_params:
            url = f"{url}?{urlencode(query_params)}"

        # Make request
        try:
            async with self.session.get(url) as response:
                # Handle rate limiting (429)
                if response.status == 429:
                    raise RateLimitError(
                        "Rate limit exceeded. Please reduce request frequency."
                    )

                # Handle other errors
                if response.status >= 400:
                    error_text = await response.text()
                    raise FMPAPIError(
                        f"API error {response.status}: {error_text}"
                    )

                # Parse JSON response
                data = await response.json()

                # FMP sometimes returns errors in JSON with 200 status
                if isinstance(data, dict) and "Error Message" in data:
                    raise FMPAPIError(f"API error: {data['Error Message']}")

                return data

        except aiohttp.ClientError as e:
            raise FMPAPIError(f"HTTP client error: {str(e)}") from e
        except asyncio.TimeoutError as e:
            raise FMPAPIError(f"Request timeout after {self.config.request_timeout}s") from e

    async def fetch_json(
        self,
        endpoint: Endpoint,
        path_params: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch JSON data from API.

        Convenience wrapper around fetch() that ensures dict response.

        Args:
            endpoint: API endpoint
            path_params: Path parameters
            query_params: Query parameters

        Returns:
            JSON response as dictionary
        """
        data = await self.fetch(endpoint, path_params, query_params)
        if not isinstance(data, dict):
            # Wrap list responses in a dict
            return {"data": data}
        return data

    async def fetch_list(
        self,
        endpoint: Endpoint,
        path_params: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> list:
        """Fetch list data from API.

        Convenience wrapper around fetch() that ensures list response.

        Args:
            endpoint: API endpoint
            path_params: Path parameters
            query_params: Query parameters

        Returns:
            JSON response as list
        """
        data = await self.fetch(endpoint, path_params, query_params)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Some endpoints wrap lists in a dict
            if "data" in data:
                return data["data"]
            # Return as single-item list
            return [data]
        return []

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status.

        Returns:
            Dictionary with rate limit information
        """
        return self.rate_limiter.get_status()

    def set_rate_limit(self, calls_per_minute: int) -> None:
        """Update rate limit.

        Args:
            calls_per_minute: New rate limit
        """
        self.rate_limiter = RateLimiter(calls_per_minute)
