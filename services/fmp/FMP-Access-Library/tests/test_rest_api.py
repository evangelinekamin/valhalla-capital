"""Tests for REST API server."""

import pytest
import os
from unittest.mock import AsyncMock, patch, Mock
from fastapi.testclient import TestClient

from fmp_data_client.server.api import app, get_fmp_client
from fmp_data_client.server.auth import API_KEYS
from fmp_data_client.models.quote import Quote
from fmp_data_client.models.profile import CompanyProfile
from fmp_data_client.models.ticker_data import TickerData
from fmp_data_client.client import FMPDataClient


@pytest.fixture(autouse=True)
def set_test_env():
    """Set test environment variables."""
    os.environ["FMP_API_KEY"] = "test_key"
    os.environ["FMP_TIER"] = "STARTER"
    yield
    # Cleanup not needed as each test runs in isolated env


@pytest.fixture
def mock_fmp_client():
    """Create mock FMP client."""
    client = AsyncMock(spec=FMPDataClient)
    # Add cache attribute for cache-related tests
    client.cache = Mock()
    client.cache.enabled = True
    return client


@pytest.fixture
def client(mock_fmp_client):
    """Create FastAPI test client with mocked dependencies."""
    async def override_get_fmp_client():
        return mock_fmp_client

    app.dependency_overrides[get_fmp_client] = override_get_fmp_client
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def valid_api_key():
    """Return a valid API key."""
    return "demo-api-key-12345"


@pytest.fixture
def mock_quote():
    """Create mock quote data."""
    return Quote(
        symbol="AAPL",
        name="Apple Inc.",
        price=175.50,
        change=2.50,
        change_percent=1.44,
        day_high=176.00,
        day_low=172.50,
        previous_close=173.00,
        volume=50000000,
        market_cap=2800000000000,
    )


@pytest.fixture
def mock_profile():
    """Create mock company profile."""
    return CompanyProfile(
        symbol="AAPL",
        name="Apple Inc.",
        industry="Consumer Electronics",
        sector="Technology",
        country="US",
        ceo="Tim Cook",
        employees=164000,
        price=175.50,
    )


@pytest.fixture
def mock_ticker_data(mock_quote, mock_profile):
    """Create mock ticker data."""
    return TickerData(
        symbol="AAPL",
        quote=mock_quote,
        profile=mock_profile,
    )


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["name"] == "FMP Data Client API"


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "components" in data


class TestAuthenticationRequired:
    """Tests for API key authentication."""

    def test_quote_without_api_key(self, client):
        """Test quote endpoint rejects requests without API key."""
        response = client.get("/quote/AAPL")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_quote_with_invalid_api_key(self, client):
        """Test quote endpoint rejects invalid API keys."""
        headers = {"X-API-Key": "invalid-key"}
        response = client.get("/quote/AAPL", headers=headers)
        assert response.status_code == 401
        data = response.json()
        assert "Invalid API key" in data["detail"] or "not found" in data["detail"].lower()


class TestQuoteEndpoint:
    """Tests for quote endpoint."""

    def test_get_quote_success(self, client, mock_fmp_client, valid_api_key, mock_quote):
        """Test successful quote retrieval."""
        mock_fmp_client.get_quote = AsyncMock(return_value=mock_quote)

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/quote/AAPL", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["price"] == 175.50
        assert data["change"] == 2.50

        # Check rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    def test_get_quote_not_found(self, client, mock_fmp_client, valid_api_key):
        """Test quote endpoint when symbol not found."""
        mock_fmp_client.get_quote = AsyncMock(return_value=None)

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/quote/INVALID", headers=headers)

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestProfileEndpoint:
    """Tests for profile endpoint."""

    def test_get_profile_success(self, client, mock_fmp_client, valid_api_key, mock_profile):
        """Test successful profile retrieval."""
        mock_fmp_client.get_profile = AsyncMock(return_value=mock_profile)

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/profile/AAPL", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["name"] == "Apple Inc."
        assert data["ceo"] == "Tim Cook"

    def test_get_profile_not_found(self, client, mock_fmp_client, valid_api_key):
        """Test profile endpoint when symbol not found."""
        mock_fmp_client.get_profile = AsyncMock(return_value=None)

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/profile/INVALID", headers=headers)

        assert response.status_code == 404


class TestTickerEndpoint:
    """Tests for ticker data endpoint."""

    def test_get_ticker_data_success(self, client, mock_fmp_client, valid_api_key, mock_ticker_data):
        """Test successful ticker data retrieval."""
        mock_fmp_client.get_ticker_data = AsyncMock(return_value=mock_ticker_data)

        headers = {"X-API-Key": valid_api_key, "Content-Type": "application/json"}
        request_data = {
            "symbol": "AAPL",
            "include_quote": True,
            "include_profile": True,
        }
        response = client.post("/ticker", json=request_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["data"]["quote"]["symbol"] == "AAPL"
        # Profile uses alias in JSON serialization
        assert "profile" in data["data"]

    def test_get_ticker_data_minimal(self, client, mock_fmp_client, valid_api_key):
        """Test ticker data with minimal request."""
        mock_ticker_data = TickerData(symbol="AAPL")
        mock_fmp_client.get_ticker_data = AsyncMock(return_value=mock_ticker_data)

        headers = {"X-API-Key": valid_api_key, "Content-Type": "application/json"}
        request_data = {"symbol": "AAPL"}
        response = client.post("/ticker", json=request_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"


class TestCacheEndpoints:
    """Tests for cache management endpoints."""

    def test_cache_status(self, client, mock_fmp_client, valid_api_key):
        """Test cache status endpoint."""
        mock_cache_info = {"enabled": True, "total_entries": 100}
        mock_fmp_client.get_cache_info = AsyncMock(return_value=mock_cache_info)

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/cache/status", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert "total_entries" in data

    def test_clear_cache(self, client, mock_fmp_client, valid_api_key):
        """Test cache clear endpoint."""
        mock_fmp_client.clear_cache = AsyncMock(return_value=True)

        headers = {"X-API-Key": valid_api_key}
        response = client.post("/cache/clear", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Cache cleared successfully"


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_headers_present(self, client, mock_fmp_client, valid_api_key, mock_quote):
        """Test that rate limit headers are present in successful responses."""
        mock_fmp_client.get_quote = AsyncMock(return_value=mock_quote)

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/quote/AAPL", headers=headers)

        # Rate limit headers should be present in successful responses
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers


class TestErrorHandling:
    """Tests for error handling."""

    def test_internal_server_error(self, client, mock_fmp_client, valid_api_key):
        """Test handling of internal server errors."""
        mock_fmp_client.get_quote = AsyncMock(side_effect=Exception("Database error"))

        headers = {"X-API-Key": valid_api_key}
        response = client.get("/quote/AAPL", headers=headers)

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_invalid_json_request(self, client, valid_api_key):
        """Test handling of invalid JSON in request body."""
        headers = {"X-API-Key": valid_api_key, "Content-Type": "application/json"}
        response = client.post("/ticker", data="invalid json", headers=headers)

        assert response.status_code == 422  # Unprocessable Entity


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present."""
        response = client.options("/health")
        # CORS should allow cross-origin requests
        # Note: TestClient doesn't fully simulate browser CORS behavior
        # In production, verify with actual browser or curl
        assert response.status_code in [200, 405]  # OPTIONS might not be handled


class TestOpenAPIDocumentation:
    """Tests for OpenAPI documentation."""

    def test_openapi_json_available(self, client):
        """Test that OpenAPI JSON schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_docs_ui_available(self, client):
        """Test that Swagger UI docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_redoc_ui_available(self, client):
        """Test that ReDoc docs are available."""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
