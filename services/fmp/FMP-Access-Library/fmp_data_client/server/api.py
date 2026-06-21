"""FastAPI REST API server for FMP Data Client."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..client import FMPDataClient
from ..config import FMPConfig
from ..models.request import DataRequest
from .auth import (
    check_rate_limit,
    get_rate_limit_headers,
    validate_api_key,
)
from .models import (
    CacheStatusResponse,
    ErrorResponse,
    HealthResponse,
    ProfileResponse,
    QuoteResponse,
    SuccessResponse,
    TickerDataResponse,
)

logger = logging.getLogger(__name__)

# API version
API_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    config = FMPConfig.from_env()
    client = FMPDataClient(config)
    await client.fetcher.start()
    app.state.fmp_client = client
    yield
    await client.fetcher.close()
    if client.cache:
        client.cache.close()


# Create FastAPI app
app = FastAPI(
    title="FMP Data Client API",
    description="REST API for Financial Modeling Prep data with caching and LLM summarization",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
_cors_origins_str = os.getenv("FMP_CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
_cors_origins = [origin.strip() for origin in _cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_fmp_client() -> FMPDataClient:
    """Get FMP client instance from app state.

    Returns:
        FMP client instance
    """
    return app.state.fmp_client


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again later.",
            "status_code": 500,
        },
    )


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "FMP Data Client API",
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint.

    Returns:
        Health status of API and components
    """
    client = await get_fmp_client()

    components = {
        "api": "healthy",
        "fmp_client": "healthy",
    }

    # Check cache if enabled
    if client.cache:
        try:
            # Test cache connection with a simple ping
            conn = client.cache.pool.get_connection()
            conn.ping(reconnect=True)
            conn.close()
            components["cache"] = "healthy"
        except Exception:
            components["cache"] = "unhealthy"
    else:
        components["cache"] = "disabled"

    # Determine overall status
    overall_status = "healthy"
    if "unhealthy" in components.values():
        overall_status = "unhealthy"
    elif "degraded" in components.values():
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=API_VERSION,
        timestamp=datetime.now().isoformat(),
        components=components,
    )


@app.get("/quote/{symbol}", response_model=QuoteResponse)
async def get_quote(
    symbol: str,
    response: Response,
    key_data: Dict = Depends(validate_api_key),
    client: FMPDataClient = Depends(get_fmp_client),
):
    """Get real-time quote for a symbol.

    Args:
        symbol: Stock ticker symbol
        response: Response object for headers
        key_data: Validated API key data
        client: FMP client instance

    Returns:
        Quote data

    Raises:
        HTTPException: If quote fetch fails
    """
    # Check rate limit
    api_key = response.headers.get("X-API-Key")
    check_rate_limit(api_key, key_data)

    # Add rate limit headers
    headers = get_rate_limit_headers(api_key, key_data)
    for header, value in headers.items():
        response.headers[header] = value

    try:
        quote = await client.get_quote(symbol)
        if not quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Quote not found for symbol: {symbol}",
            )

        return QuoteResponse(
            symbol=quote.symbol,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            day_high=quote.day_high,
            day_low=quote.day_low,
            previous_close=quote.previous_close,
            market_cap=quote.market_cap,
            timestamp=quote.timestamp,
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is (e.g., 404 Not Found)
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch quote: {str(e)}",
        )


@app.get("/profile/{symbol}", response_model=ProfileResponse)
async def get_profile(
    symbol: str,
    response: Response,
    key_data: Dict = Depends(validate_api_key),
    client: FMPDataClient = Depends(get_fmp_client),
):
    """Get company profile for a symbol.

    Args:
        symbol: Stock ticker symbol
        response: Response object for headers
        key_data: Validated API key data
        client: FMP client instance

    Returns:
        Company profile data

    Raises:
        HTTPException: If profile fetch fails
    """
    # Check rate limit
    api_key = response.headers.get("X-API-Key")
    check_rate_limit(api_key, key_data)

    # Add rate limit headers
    headers = get_rate_limit_headers(api_key, key_data)
    for header, value in headers.items():
        response.headers[header] = value

    try:
        profile = await client.get_profile(symbol)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile not found for symbol: {symbol}",
            )

        return ProfileResponse(
            symbol=profile.symbol,
            name=profile.name,
            sector=profile.sector,
            industry=profile.industry,
            description=profile.description,
            ceo=profile.ceo,
            employees=profile.employees,
            website=profile.website,
            country=profile.country,
            market_cap=profile.market_cap,
            exchange=profile.exchange,
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is (e.g., 404 Not Found)
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profile: {str(e)}",
        )


@app.post("/ticker", response_model=TickerDataResponse)
async def get_ticker_data(
    request: DataRequest,
    response: Response,
    key_data: Dict = Depends(validate_api_key),
    client: FMPDataClient = Depends(get_fmp_client),
):
    """Get comprehensive ticker data based on request specification.

    Args:
        request: Data request specification
        response: Response object for headers
        key_data: Validated API key data
        client: FMP client instance

    Returns:
        Comprehensive ticker data

    Raises:
        HTTPException: If data fetch fails
    """
    # Check rate limit
    api_key = response.headers.get("X-API-Key")
    check_rate_limit(api_key, key_data)

    # Add rate limit headers
    headers = get_rate_limit_headers(api_key, key_data)
    for header, value in headers.items():
        response.headers[header] = value

    try:
        ticker_data = await client.get_ticker_data(request)

        return TickerDataResponse(
            symbol=ticker_data.symbol,
            data=ticker_data.model_dump(exclude_none=True),
            cached=ticker_data.cache_hit or False,
            fetched_at=ticker_data.fetched_at,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch ticker data: {str(e)}",
        )


@app.get("/cache/status", response_model=CacheStatusResponse)
async def get_cache_status(
    response: Response,
    key_data: Dict = Depends(validate_api_key),
    client: FMPDataClient = Depends(get_fmp_client),
):
    """Get cache status and statistics.

    Args:
        response: Response object for headers
        key_data: Validated API key data
        client: FMP client instance

    Returns:
        Cache status information
    """
    # Check rate limit
    api_key = response.headers.get("X-API-Key")
    check_rate_limit(api_key, key_data)

    # Add rate limit headers
    headers = get_rate_limit_headers(api_key, key_data)
    for header, value in headers.items():
        response.headers[header] = value

    if not client.cache:
        return CacheStatusResponse(
            enabled=False,
            total_entries=None,
            hit_rate=None,
            stats=None,
        )

    try:
        cache_info = await client.get_cache_info()
        return CacheStatusResponse(
            enabled=True,
            total_entries=cache_info.get("ticker_cache_entries"),
            hit_rate=None,
            stats=cache_info,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache status: {str(e)}",
        )


@app.post("/cache/clear", response_model=SuccessResponse)
async def clear_cache(
    response: Response,
    key_data: Dict = Depends(validate_api_key),
    client: FMPDataClient = Depends(get_fmp_client),
):
    """Clear all cached data.

    Args:
        response: Response object for headers
        key_data: Validated API key data
        client: FMP client instance

    Returns:
        Success response
    """
    # Check rate limit
    api_key = response.headers.get("X-API-Key")
    check_rate_limit(api_key, key_data)

    # Add rate limit headers
    headers = get_rate_limit_headers(api_key, key_data)
    for header, value in headers.items():
        response.headers[header] = value

    if not client.cache:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cache is not enabled",
        )

    try:
        await client.clear_cache()
        return SuccessResponse(
            success=True,
            message="Cache cleared successfully",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
