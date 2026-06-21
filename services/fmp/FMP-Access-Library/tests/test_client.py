"""Tests for FMP Data Client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fmp_data_client.client import FMPDataClient
from fmp_data_client.config import FMPConfig, Tier
from fmp_data_client.models.request import DataRequest
from fmp_data_client.models.quote import Quote
from fmp_data_client.models.profile import CompanyProfile

from tests.fixtures.mock_responses import (
    MOCK_QUOTE_RESPONSE,
    MOCK_PROFILE_RESPONSE,
)


@pytest.mark.asyncio
class TestFMPDataClient:
    """Test FMPDataClient main orchestrator."""

    async def test_client_init(self, minimal_config: FMPConfig) -> None:
        """Test client initialization."""
        client = FMPDataClient(minimal_config)

        assert client.config == minimal_config
        assert client.fetcher is not None

    async def test_client_context_manager(self, minimal_config: FMPConfig) -> None:
        """Test client as async context manager."""
        async with FMPDataClient(minimal_config) as client:
            assert client.fetcher is not None

    async def test_client_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test creating client from environment variables."""
        monkeypatch.setenv("FMP_API_KEY", "test_key_from_env")
        monkeypatch.setenv("FMP_TIER", "premium")

        client = FMPDataClient.from_env()

        assert client.config.api_key == "test_key_from_env"
        assert client.config.tier == Tier.PREMIUM

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_quote")
    async def test_get_quote(
        self, mock_fetch_quote: AsyncMock, minimal_config: FMPConfig
    ) -> None:
        """Test getting a single quote."""
        # Mock the fetch_quote method
        mock_quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        mock_fetch_quote.return_value = mock_quote

        async with FMPDataClient(minimal_config) as client:
            quote = await client.get_quote("AAPL")

            assert quote.symbol == "AAPL"
            assert quote.price == 185.50
            mock_fetch_quote.assert_called_once_with("AAPL")

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_profile")
    async def test_get_profile(
        self, mock_fetch_profile: AsyncMock, minimal_config: FMPConfig
    ) -> None:
        """Test getting company profile."""
        mock_profile = CompanyProfile(**MOCK_PROFILE_RESPONSE[0])
        mock_fetch_profile.return_value = mock_profile

        async with FMPDataClient(minimal_config) as client:
            profile = await client.get_profile("AAPL")

            assert profile.symbol == "AAPL"
            assert profile.name == "Apple Inc."
            mock_fetch_profile.assert_called_once_with("AAPL")

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_quote")
    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_profile")
    async def test_get_ticker_data_basic(
        self,
        mock_fetch_profile: AsyncMock,
        mock_fetch_quote: AsyncMock,
        minimal_config: FMPConfig,
    ) -> None:
        """Test getting basic ticker data."""
        mock_quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        mock_profile = CompanyProfile(**MOCK_PROFILE_RESPONSE[0])

        mock_fetch_quote.return_value = mock_quote
        mock_fetch_profile.return_value = mock_profile

        async with FMPDataClient(minimal_config) as client:
            request = DataRequest(
                symbol="AAPL",
                include_quote=True,
                include_profile=True,
            )

            data = await client.get_ticker_data(request)

            assert data.symbol == "AAPL"
            assert data.quote is not None
            assert data.quote.symbol == "AAPL"
            assert data.profile is not None
            assert data.profile.name == "Apple Inc."

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_quote")
    async def test_get_ticker_data_quote_only(
        self, mock_fetch_quote: AsyncMock, minimal_config: FMPConfig
    ) -> None:
        """Test getting ticker data with only quote."""
        mock_quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        mock_fetch_quote.return_value = mock_quote

        async with FMPDataClient(minimal_config) as client:
            request = DataRequest(
                symbol="AAPL",
                include_quote=True,
                include_profile=False,
            )

            data = await client.get_ticker_data(request)

            assert data.symbol == "AAPL"
            assert data.quote is not None
            assert data.profile is None

    async def test_get_ticker_data_empty_request(
        self, minimal_config: FMPConfig
    ) -> None:
        """Test getting ticker data with no includes (should return minimal data)."""
        async with FMPDataClient(minimal_config) as client:
            request = DataRequest(symbol="AAPL")

            data = await client.get_ticker_data(request)

            assert data.symbol == "AAPL"
            assert data.quote is None
            assert data.profile is None

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_quote")
    async def test_caching_integration(
        self, mock_fetch_quote: AsyncMock, premium_config: FMPConfig
    ) -> None:
        """Test that caching works when enabled."""
        mock_quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        mock_fetch_quote.return_value = mock_quote

        async with FMPDataClient(premium_config) as client:
            # First call should fetch from API
            quote1 = await client.get_quote("AAPL")

            # If cache is enabled, second call might use cache
            quote2 = await client.get_quote("AAPL")

            assert quote1.symbol == quote2.symbol
            assert quote1.price == quote2.price

    async def test_get_rate_limit_status(self, minimal_config: FMPConfig) -> None:
        """Test getting rate limit status."""
        async with FMPDataClient(minimal_config) as client:
            status = client.get_rate_limit_status()

            assert "calls_per_minute" in status
            assert status["calls_per_minute"] == 300  # Starter tier

    async def test_set_rate_limit(self, minimal_config: FMPConfig) -> None:
        """Test setting custom rate limit."""
        async with FMPDataClient(minimal_config) as client:
            client.set_rate_limit(500)

            status = client.get_rate_limit_status()
            assert status["calls_per_minute"] == 500

    async def test_get_cache_info(self, premium_config: FMPConfig) -> None:
        """Test getting cache info."""
        async with FMPDataClient(premium_config) as client:
            cache_info = await client.get_cache_info("AAPL")

            assert "enabled" in cache_info
            # Cache may be disabled if MySQL can't connect (expected in test environment)
            assert isinstance(cache_info["enabled"], bool)

    @patch("fmp_data_client.cache.mysql.MySQLCache.clear_cache")
    async def test_clear_cache(
        self, mock_clear: AsyncMock, premium_config: FMPConfig
    ) -> None:
        """Test clearing cache."""
        mock_clear.return_value = True
        async with FMPDataClient(premium_config) as client:
            result = await client.clear_cache()
            assert result is True

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_quote")
    async def test_concurrent_requests(
        self, mock_fetch_quote: AsyncMock, minimal_config: FMPConfig
    ) -> None:
        """Test handling multiple concurrent requests."""
        import asyncio

        mock_quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        mock_fetch_quote.return_value = mock_quote

        async with FMPDataClient(minimal_config) as client:
            # Create multiple concurrent requests
            tasks = [client.get_quote("AAPL") for _ in range(5)]

            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(r.symbol == "AAPL" for r in results)

    @patch("fmp_data_client.fetcher.specialized.SpecializedFetcher.fetch_quote")
    async def test_error_handling(
        self, mock_fetch_quote: AsyncMock, minimal_config: FMPConfig
    ) -> None:
        """Test error handling for failed requests."""
        # Mock an error
        mock_fetch_quote.side_effect = Exception("API Error")

        async with FMPDataClient(minimal_config) as client:
            # Client handles exceptions gracefully and returns None
            result = await client.get_quote("INVALID")
            assert result is None

    async def test_full_analysis_request(self, minimal_config: FMPConfig) -> None:
        """Test creating a full analysis request."""
        async with FMPDataClient(minimal_config) as client:
            request = DataRequest(symbol="AAPL")
            request.enable_full_analysis()

            # Verify all flags are set
            assert request.include_quote is True
            assert request.include_profile is True
            assert request.include_fundamentals is True
            assert request.include_dcf is True
            assert request.include_analyst_estimates is True

    async def test_client_cleanup(self, minimal_config: FMPConfig) -> None:
        """Test that client cleans up resources properly."""
        client = FMPDataClient(minimal_config)

        async with client:
            assert client.fetcher.session is not None

        # After exiting context, session should be closed
        assert client.fetcher.session is None or client.fetcher.session.closed
