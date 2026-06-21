"""MySQL-based cache implementation."""

import asyncio
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.pooling import MySQLConnectionPool

from ..config import FMPConfig
from .ttl import get_ttl_duration, should_cache

logger = logging.getLogger(__name__)


class MySQLCache:
    """MySQL-based cache for FMP data.

    Implements caching with intelligent TTL policies and graceful degradation.
    """

    def __init__(self, config: FMPConfig):
        """Initialize MySQL cache.

        Args:
            config: FMP configuration
        """
        self.config = config
        self.pool: Optional[MySQLConnectionPool] = None
        self.enabled = config.cache_enabled
        self._initialized = False

        if self.enabled:
            self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Initialize MySQL connection pool."""
        try:
            self.pool = MySQLConnectionPool(
                pool_name="fmp_cache_pool",
                pool_size=self.config.mysql_pool_size,
                host=self.config.mysql_host,
                port=self.config.mysql_port,
                user=self.config.mysql_user,
                password=self.config.mysql_password,
                database=self.config.mysql_database,
                autocommit=True,
            )
            self._initialized = True
            logger.info("MySQL cache pool initialized successfully")
        except MySQLError as e:
            logger.error(f"Failed to initialize MySQL cache: {e}")
            self.enabled = False
            self._initialized = False

    @contextmanager
    def _get_connection(self):
        """Get connection from pool.

        Yields:
            MySQL connection

        Raises:
            RuntimeError: If cache is not available
        """
        if not self.enabled or not self.pool:
            raise RuntimeError("MySQL cache is not enabled or available")

        conn = None
        try:
            conn = self.pool.get_connection()
            yield conn
        except MySQLError as e:
            logger.error(f"MySQL connection error: {e}")
            raise
        finally:
            if conn and conn.is_connected():
                conn.close()

    async def get(
        self,
        symbol: str,
        data_type: str,
        period_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve data from cache.

        Args:
            symbol: Stock ticker symbol
            data_type: Type of data
            period_key: Optional period key for time-series data

        Returns:
            Cached data dict or None if not found/expired
        """
        if not self.enabled:
            return None

        if not should_cache(data_type):
            return None

        try:
            def _get():
                with self._get_connection() as conn:
                    cursor = conn.cursor(dictionary=True)

                    query = """
                        SELECT data, expires_at
                        FROM ticker_cache
                        WHERE symbol = %s
                          AND data_type = %s
                          AND (period_key = %s OR (period_key IS NULL AND %s IS NULL))
                    """
                    cursor.execute(query, (symbol, data_type, period_key, period_key))
                    result = cursor.fetchone()
                    cursor.close()

                    if not result:
                        return None

                    # Check if expired
                    if result["expires_at"] and datetime.now() > result["expires_at"]:
                        # Delete expired entry
                        self._delete_cache_entry(symbol, data_type, period_key)
                        return None

                    return json.loads(result["data"])

            # Run in thread pool to avoid blocking
            return await asyncio.to_thread(_get)

        except Exception as e:
            logger.error(f"Cache get error for {symbol}/{data_type}: {e}")
            return None

    async def set(
        self,
        symbol: str,
        data_type: str,
        data: Dict[str, Any],
        period_key: Optional[str] = None,
    ) -> bool:
        """Store data in cache.

        Args:
            symbol: Stock ticker symbol
            data_type: Type of data
            data: Data to cache
            period_key: Optional period key for time-series data

        Returns:
            True if successfully cached
        """
        if not self.enabled:
            return False

        if not should_cache(data_type):
            return False

        try:
            def _set():
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Calculate expiration
                    ttl_duration = get_ttl_duration(data_type)
                    expires_at = None
                    if ttl_duration:
                        expires_at = datetime.now() + ttl_duration

                    # Insert or update
                    query = """
                        INSERT INTO ticker_cache
                        (symbol, data_type, period_key, data, expires_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        data = VALUES(data),
                        created_at = CURRENT_TIMESTAMP,
                        expires_at = VALUES(expires_at)
                    """

                    cursor.execute(
                        query,
                        (
                            symbol,
                            data_type,
                            period_key,
                            json.dumps(data),
                            expires_at,
                        ),
                    )
                    cursor.close()
                    return True

            return await asyncio.to_thread(_set)

        except Exception as e:
            logger.error(f"Cache set error for {symbol}/{data_type}: {e}")
            return False

    def _delete_cache_entry(
        self,
        symbol: str,
        data_type: str,
        period_key: Optional[str] = None,
    ) -> None:
        """Delete a specific cache entry.

        Args:
            symbol: Stock ticker symbol
            data_type: Type of data
            period_key: Optional period key
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    DELETE FROM ticker_cache
                    WHERE symbol = %s
                      AND data_type = %s
                      AND (period_key = %s OR (period_key IS NULL AND %s IS NULL))
                """
                cursor.execute(query, (symbol, data_type, period_key, period_key))
                cursor.close()
        except Exception as e:
            logger.error(f"Error deleting cache entry: {e}")

    async def get_summary(
        self,
        summary_type: str,
        **keys: Any,
    ) -> Optional[Dict[str, Any]]:
        """Get a cached summary (transcript or filing).

        Args:
            summary_type: 'transcript' or 'filing'
            **keys: Lookup keys (symbol, year, quarter for transcripts, etc.)

        Returns:
            Cached summary or None
        """
        if not self.enabled:
            return None

        try:
            def _get_summary():
                with self._get_connection() as conn:
                    cursor = conn.cursor(dictionary=True)

                    if summary_type == "transcript":
                        query = """
                            SELECT summary
                            FROM transcript_summaries
                            WHERE symbol = %s AND year = %s AND quarter = %s
                        """
                        cursor.execute(
                            query,
                            (keys["symbol"], keys["year"], keys["quarter"])
                        )
                    elif summary_type == "filing":
                        query = """
                            SELECT summary
                            FROM filing_summaries
                            WHERE accession_number = %s
                        """
                        cursor.execute(query, (keys["accession_number"],))
                    else:
                        return None

                    result = cursor.fetchone()
                    cursor.close()

                    if result:
                        return json.loads(result["summary"])
                    return None

            return await asyncio.to_thread(_get_summary)

        except Exception as e:
            logger.error(f"Error getting {summary_type} summary: {e}")
            return None

    async def set_summary(
        self,
        summary_type: str,
        data: Dict[str, Any],
        **keys: Any,
    ) -> bool:
        """Cache a summary (transcript or filing).

        Args:
            summary_type: 'transcript' or 'filing'
            data: Summary data to cache
            **keys: Lookup keys

        Returns:
            True if successfully cached
        """
        if not self.enabled:
            return False

        try:
            def _set_summary():
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    if summary_type == "transcript":
                        query = """
                            INSERT INTO transcript_summaries
                            (symbol, year, quarter, summary, model_used)
                            VALUES (%s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            summary = VALUES(summary),
                            model_used = VALUES(model_used)
                        """
                        cursor.execute(
                            query,
                            (
                                keys["symbol"],
                                keys["year"],
                                keys["quarter"],
                                json.dumps(data),
                                keys.get("model_used"),
                            ),
                        )
                    elif summary_type == "filing":
                        query = """
                            INSERT INTO filing_summaries
                            (symbol, accession_number, filing_type, filing_date, summary, model_used)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            summary = VALUES(summary),
                            model_used = VALUES(model_used)
                        """
                        cursor.execute(
                            query,
                            (
                                keys["symbol"],
                                keys["accession_number"],
                                keys["filing_type"],
                                keys["filing_date"],
                                json.dumps(data),
                                keys.get("model_used"),
                            ),
                        )
                    else:
                        return False

                    cursor.close()
                    return True

            return await asyncio.to_thread(_set_summary)

        except Exception as e:
            logger.error(f"Error setting {summary_type} summary: {e}")
            return False

    async def clear_cache(self, symbol: Optional[str] = None) -> bool:
        """Clear cache entries.

        Args:
            symbol: Optional symbol to clear (clears all if None)

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        try:
            def _clear():
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    if symbol:
                        # Clear specific symbol
                        cursor.execute(
                            "DELETE FROM ticker_cache WHERE symbol = %s",
                            (symbol,)
                        )
                        cursor.execute(
                            "DELETE FROM transcript_summaries WHERE symbol = %s",
                            (symbol,)
                        )
                        cursor.execute(
                            "DELETE FROM filing_summaries WHERE symbol = %s",
                            (symbol,)
                        )
                    else:
                        # Clear all cache
                        cursor.execute("TRUNCATE TABLE ticker_cache")
                        cursor.execute("TRUNCATE TABLE transcript_summaries")
                        cursor.execute("TRUNCATE TABLE filing_summaries")

                    cursor.close()
                    return True

            return await asyncio.to_thread(_clear)

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False

    async def get_cache_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get cache information, optionally filtered by symbol.

        Args:
            symbol: Optional stock ticker symbol for per-symbol stats

        Returns:
            Dictionary with cache statistics
        """
        if not self.enabled:
            return {"enabled": False}

        try:
            def _get_info():
                with self._get_connection() as conn:
                    cursor = conn.cursor(dictionary=True)

                    if symbol:
                        # Per-symbol counts
                        cursor.execute(
                            "SELECT COUNT(*) as count FROM ticker_cache WHERE symbol = %s",
                            (symbol,)
                        )
                        ticker_count = cursor.fetchone()["count"]

                        cursor.execute(
                            "SELECT COUNT(*) as count FROM transcript_summaries WHERE symbol = %s",
                            (symbol,)
                        )
                        transcript_count = cursor.fetchone()["count"]

                        cursor.execute(
                            "SELECT COUNT(*) as count FROM filing_summaries WHERE symbol = %s",
                            (symbol,)
                        )
                        filing_count = cursor.fetchone()["count"]
                    else:
                        # Overall counts
                        cursor.execute("SELECT COUNT(*) as count FROM ticker_cache")
                        ticker_count = cursor.fetchone()["count"]

                        cursor.execute("SELECT COUNT(*) as count FROM transcript_summaries")
                        transcript_count = cursor.fetchone()["count"]

                        cursor.execute("SELECT COUNT(*) as count FROM filing_summaries")
                        filing_count = cursor.fetchone()["count"]

                    cursor.close()

                    info = {
                        "enabled": True,
                        "ticker_cache_entries": ticker_count,
                        "transcript_summaries": transcript_count,
                        "filing_summaries": filing_count,
                    }
                    if symbol:
                        info["symbol"] = symbol
                    return info

            return await asyncio.to_thread(_get_info)

        except Exception as e:
            logger.error(f"Error getting cache info: {e}")
            return {"enabled": True, "error": str(e)}

    async def cleanup_expired(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        try:
            def _cleanup():
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        DELETE FROM ticker_cache
                        WHERE expires_at IS NOT NULL
                          AND expires_at < NOW()
                        """
                    )
                    count = cursor.rowcount
                    cursor.close()
                    return count

            return await asyncio.to_thread(_cleanup)

        except Exception as e:
            logger.error(f"Error cleaning up expired cache: {e}")
            return 0

    def close(self) -> None:
        """Close connection pool."""
        if self.pool:
            # Connection pools don't have explicit close in mysql-connector-python
            # Connections are closed when the pool is garbage collected
            self.pool = None
            self._initialized = False
