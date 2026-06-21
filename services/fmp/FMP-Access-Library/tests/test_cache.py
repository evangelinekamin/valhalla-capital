"""Tests for cache module."""

import json
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest

from fmp_data_client.cache.mysql import MySQLCache
from fmp_data_client.cache.ttl import (
    CachePolicy,
    DATA_TYPE_POLICIES,
    POLICY_DURATIONS,
    get_cache_policy,
    get_ttl_duration,
    should_cache,
)
from fmp_data_client.config import FMPConfig, Tier


# ============================================================================
# TTL Policy Tests
# ============================================================================


class TestCachePolicy:
    """Tests for cache policy enum and mappings."""

    def test_policy_durations(self):
        """Test that policy durations are correctly defined."""
        assert POLICY_DURATIONS[CachePolicy.PERMANENT] is None
        assert POLICY_DURATIONS[CachePolicy.LONG] == timedelta(hours=24)
        assert POLICY_DURATIONS[CachePolicy.MEDIUM] == timedelta(hours=6)
        assert POLICY_DURATIONS[CachePolicy.SHORT] == timedelta(hours=1)
        assert POLICY_DURATIONS[CachePolicy.VERY_SHORT] == timedelta(minutes=15)
        assert POLICY_DURATIONS[CachePolicy.NONE] is None

    def test_data_type_policies_coverage(self):
        """Test that critical data types have policies defined."""
        critical_types = [
            "quote",
            "profile",
            "income_statements",
            "analyst_estimates",
            "institutional_holders",
            "news",
        ]
        for data_type in critical_types:
            assert data_type in DATA_TYPE_POLICIES

    def test_permanent_data_types(self):
        """Test that historical data has permanent caching."""
        permanent_types = [
            "dividends",
            "splits",
            "income_statements",
            "balance_sheets",
            "cash_flow_statements",
            "historical_prices",
            "transcripts",
            "sec_filings",
        ]
        for data_type in permanent_types:
            assert DATA_TYPE_POLICIES[data_type] == CachePolicy.PERMANENT

    def test_short_ttl_real_time_data(self):
        """Test that real-time data has short TTL."""
        assert DATA_TYPE_POLICIES["quote"] == CachePolicy.VERY_SHORT
        assert DATA_TYPE_POLICIES["aftermarket_quote"] == CachePolicy.VERY_SHORT


class TestGetCachePolicy:
    """Tests for get_cache_policy() function."""

    def test_get_known_policy(self):
        """Test getting policy for known data type."""
        assert get_cache_policy("quote") == CachePolicy.VERY_SHORT
        assert get_cache_policy("profile") == CachePolicy.LONG
        assert get_cache_policy("dividends") == CachePolicy.PERMANENT

    def test_get_unknown_policy_defaults_to_medium(self):
        """Test that unknown data types default to MEDIUM policy."""
        assert get_cache_policy("unknown_data_type") == CachePolicy.MEDIUM

    def test_get_all_defined_policies(self):
        """Test getting policies for all defined data types."""
        for data_type in DATA_TYPE_POLICIES:
            policy = get_cache_policy(data_type)
            assert isinstance(policy, CachePolicy)


class TestGetTTLDuration:
    """Tests for get_ttl_duration() function."""

    def test_permanent_returns_none(self):
        """Test that permanent data returns None for TTL."""
        assert get_ttl_duration("dividends") is None
        assert get_ttl_duration("income_statements") is None

    def test_quote_returns_15_minutes(self):
        """Test that quotes have 15 minute TTL."""
        ttl = get_ttl_duration("quote")
        assert ttl == timedelta(minutes=15)

    def test_profile_returns_24_hours(self):
        """Test that profile has 24 hour TTL."""
        ttl = get_ttl_duration("profile")
        assert ttl == timedelta(hours=24)

    def test_analyst_estimates_returns_1_hour(self):
        """Test that analyst estimates have 1 hour TTL."""
        ttl = get_ttl_duration("analyst_estimates")
        assert ttl == timedelta(hours=1)

    def test_unknown_type_gets_medium_ttl(self):
        """Test that unknown types get medium (6 hour) TTL."""
        ttl = get_ttl_duration("unknown_type")
        assert ttl == timedelta(hours=6)


class TestShouldCache:
    """Tests for should_cache() function."""

    def test_should_cache_normal_types(self):
        """Test that normal data types should be cached."""
        assert should_cache("quote") is True
        assert should_cache("profile") is True
        assert should_cache("income_statements") is True

    def test_should_not_cache_none_policy(self):
        """Test that NONE policy data should not be cached."""
        # First, need to test with a data type that has NONE policy
        # Since none are defined by default, test the logic
        with patch.dict(DATA_TYPE_POLICIES, {"temp_data": CachePolicy.NONE}):
            assert should_cache("temp_data") is False

    def test_should_cache_all_defined_types(self):
        """Test caching decision for all defined data types."""
        for data_type in DATA_TYPE_POLICIES:
            result = should_cache(data_type)
            assert isinstance(result, bool)
            # All current types should be cacheable
            assert result is True


# ============================================================================
# MySQLCache Tests
# ============================================================================


@pytest.fixture
def mock_config():
    """Create mock FMP config with cache enabled."""
    return FMPConfig(
        api_key="test_key",
        tier=Tier.STARTER,
        cache_enabled=True,
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="test_user",
        mysql_password="test_password",
        mysql_database="test_db",
        mysql_pool_size=5,
    )


@pytest.fixture
def mock_config_no_cache():
    """Create mock FMP config with cache disabled."""
    return FMPConfig(
        api_key="test_key",
        tier=Tier.STARTER,
        cache_enabled=False,
    )


class TestMySQLCacheInit:
    """Tests for MySQLCache initialization."""

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    def test_init_with_cache_enabled(self, mock_pool_class, mock_config):
        """Test initialization with cache enabled."""
        cache = MySQLCache(mock_config)

        assert cache.enabled is True
        assert cache._initialized is True
        mock_pool_class.assert_called_once()

    def test_init_with_cache_disabled(self, mock_config_no_cache):
        """Test initialization with cache disabled."""
        cache = MySQLCache(mock_config_no_cache)

        assert cache.enabled is False
        assert cache._initialized is False
        assert cache.pool is None

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    def test_init_mysql_connection_error(self, mock_pool_class, mock_config):
        """Test graceful degradation when MySQL connection fails."""
        from mysql.connector import Error as MySQLError

        mock_pool_class.side_effect = MySQLError("Connection failed")
        cache = MySQLCache(mock_config)

        assert cache.enabled is False
        assert cache._initialized is False


class TestMySQLCacheGet:
    """Tests for MySQLCache.get() method."""

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_disabled_cache(self, mock_pool_class, mock_config_no_cache):
        """Test get() returns None when cache disabled."""
        cache = MySQLCache(mock_config_no_cache)
        result = await cache.get("AAPL", "quote")
        assert result is None

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_non_cacheable_type(self, mock_pool_class, mock_config):
        """Test get() returns None for non-cacheable data types."""
        with patch.dict(DATA_TYPE_POLICIES, {"no_cache_type": CachePolicy.NONE}):
            cache = MySQLCache(mock_config)
            result = await cache.get("AAPL", "no_cache_type")
            assert result is None

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_cache_hit(self, mock_pool_class, mock_config):
        """Test successful cache hit."""
        # Mock the connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        # Mock database response
        test_data = {"price": 150.0, "symbol": "AAPL"}
        mock_cursor.fetchone.return_value = {
            "data": json.dumps(test_data),
            "expires_at": datetime.now() + timedelta(hours=1),
        }

        cache = MySQLCache(mock_config)
        result = await cache.get("AAPL", "quote")

        assert result == test_data
        mock_cursor.execute.assert_called_once()

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_cache_miss(self, mock_pool_class, mock_config):
        """Test cache miss returns None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        mock_cursor.fetchone.return_value = None

        cache = MySQLCache(mock_config)
        result = await cache.get("AAPL", "quote")

        assert result is None

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_expired_entry(self, mock_pool_class, mock_config):
        """Test that expired entries are deleted and None returned."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        # Expired data
        test_data = {"price": 150.0}
        mock_cursor.fetchone.return_value = {
            "data": json.dumps(test_data),
            "expires_at": datetime.now() - timedelta(hours=1),  # Expired
        }

        cache = MySQLCache(mock_config)
        result = await cache.get("AAPL", "quote")

        assert result is None


class TestMySQLCacheSet:
    """Tests for MySQLCache.set() method."""

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_disabled_cache(self, mock_pool_class, mock_config_no_cache):
        """Test set() returns False when cache disabled."""
        cache = MySQLCache(mock_config_no_cache)
        result = await cache.set("AAPL", "quote", {"price": 150.0})
        assert result is False

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_non_cacheable_type(self, mock_pool_class, mock_config):
        """Test set() returns False for non-cacheable data types."""
        with patch.dict(DATA_TYPE_POLICIES, {"no_cache_type": CachePolicy.NONE}):
            cache = MySQLCache(mock_config)
            result = await cache.set("AAPL", "no_cache_type", {"data": "value"})
            assert result is False

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_success(self, mock_pool_class, mock_config):
        """Test successful cache set."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        test_data = {"price": 150.0, "symbol": "AAPL"}
        result = await cache.set("AAPL", "quote", test_data)

        assert result is True
        mock_cursor.execute.assert_called_once()
        # Verify the data was JSON serialized
        call_args = mock_cursor.execute.call_args[0]
        assert json.dumps(test_data) in call_args[1]

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_permanent_data(self, mock_pool_class, mock_config):
        """Test setting permanent data (no expiration)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        test_data = {"dividend": 0.25}
        result = await cache.set("AAPL", "dividends", test_data)

        assert result is True
        # Verify expires_at is None for permanent data
        call_args = mock_cursor.execute.call_args[0]
        assert call_args[1][4] is None  # expires_at parameter


class TestMySQLCacheSummaries:
    """Tests for summary caching (transcripts and filings)."""

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_transcript_summary(self, mock_pool_class, mock_config):
        """Test getting cached transcript summary."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        summary_data = {"executive_summary": "Test summary"}
        mock_cursor.fetchone.return_value = {"summary": json.dumps(summary_data)}

        cache = MySQLCache(mock_config)
        result = await cache.get_summary("transcript", symbol="AAPL", year=2024, quarter=1)

        assert result == summary_data

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_transcript_summary(self, mock_pool_class, mock_config):
        """Test setting transcript summary."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        summary_data = {"executive_summary": "Test summary"}
        result = await cache.set_summary(
            "transcript",
            summary_data,
            symbol="AAPL",
            year=2024,
            quarter=1,
            model_used="claude-haiku-3.5",
        )

        assert result is True
        mock_cursor.execute.assert_called_once()

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_filing_summary(self, mock_pool_class, mock_config):
        """Test getting cached filing summary."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        summary_data = {"material_changes": ["Test change"]}
        mock_cursor.fetchone.return_value = {"summary": json.dumps(summary_data)}

        cache = MySQLCache(mock_config)
        result = await cache.get_summary("filing", accession_number="0001234567-24-000001")

        assert result == summary_data

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_filing_summary(self, mock_pool_class, mock_config):
        """Test setting filing summary."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        summary_data = {"material_changes": ["Test change"]}
        result = await cache.set_summary(
            "filing",
            summary_data,
            symbol="AAPL",
            accession_number="0001234567-24-000001",
            filing_type="10-K",
            filing_date="2024-01-15",
            model_used="claude-haiku-3.5",
        )

        assert result is True
        mock_cursor.execute.assert_called_once()


class TestMySQLCacheClearAndInfo:
    """Tests for cache clearing and info methods."""

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_clear_cache_all(self, mock_pool_class, mock_config):
        """Test clearing all cache."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        result = await cache.clear_cache()

        assert result is True
        assert mock_cursor.execute.call_count == 3  # 3 TRUNCATE calls

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_clear_cache_symbol(self, mock_pool_class, mock_config):
        """Test clearing cache for specific symbol."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        result = await cache.clear_cache("AAPL")

        assert result is True
        assert mock_cursor.execute.call_count == 3  # 3 DELETE calls

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_cache_info(self, mock_pool_class, mock_config):
        """Test getting cache info for symbol."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        # Mock count queries
        mock_cursor.fetchone.side_effect = [
            {"count": 10},  # ticker_cache_entries
            {"count": 2},  # transcript_summaries
            {"count": 5},  # filing_summaries
        ]

        cache = MySQLCache(mock_config)
        info = await cache.get_cache_info("AAPL")

        assert info["enabled"] is True
        assert info["symbol"] == "AAPL"
        assert info["ticker_cache_entries"] == 10
        assert info["transcript_summaries"] == 2
        assert info["filing_summaries"] == 5

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_cache_info_disabled(self, mock_pool_class, mock_config_no_cache):
        """Test getting cache info when cache disabled."""
        cache = MySQLCache(mock_config_no_cache)
        info = await cache.get_cache_info("AAPL")

        assert info == {"enabled": False}

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_cleanup_expired(self, mock_pool_class, mock_config):
        """Test cleanup of expired entries."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 15  # 15 rows deleted
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        count = await cache.cleanup_expired()

        assert count == 15
        mock_cursor.execute.assert_called_once()


class TestMySQLCacheErrorHandling:
    """Tests for error handling and graceful degradation."""

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_get_handles_exceptions(self, mock_pool_class, mock_config):
        """Test that get() handles exceptions gracefully."""
        mock_pool = MagicMock()
        mock_pool.get_connection.side_effect = Exception("Connection error")
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        result = await cache.get("AAPL", "quote")

        # Should return None on error
        assert result is None

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_set_handles_exceptions(self, mock_pool_class, mock_config):
        """Test that set() handles exceptions gracefully."""
        mock_pool = MagicMock()
        mock_pool.get_connection.side_effect = Exception("Connection error")
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        result = await cache.set("AAPL", "quote", {"price": 150.0})

        # Should return False on error
        assert result is False

    @patch("fmp_data_client.cache.mysql.MySQLConnectionPool")
    async def test_clear_cache_handles_exceptions(self, mock_pool_class, mock_config):
        """Test that clear_cache() handles exceptions gracefully."""
        mock_pool = MagicMock()
        mock_pool.get_connection.side_effect = Exception("Connection error")
        mock_pool_class.return_value = mock_pool

        cache = MySQLCache(mock_config)
        result = await cache.clear_cache()

        assert result is False

    def test_close(self, mock_config):
        """Test closing cache connection."""
        with patch("fmp_data_client.cache.mysql.MySQLConnectionPool"):
            cache = MySQLCache(mock_config)
            cache.close()

            assert cache.pool is None
            assert cache._initialized is False
