"""Tests for database operations."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from openinsider.models import ClusterBuy, ScrapeLog


class TestDatabaseInitialization:
    """Tests for database initialization."""

    def test_database_creation(self, temp_db):
        """Test database file is created."""
        assert temp_db.db_path is not None

    def test_tables_created(self, temp_db):
        """Test all tables are created."""
        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

        assert "cluster_buys" in tables
        assert "insider_transactions" in tables
        assert "scrape_log" in tables

    def test_indexes_created(self, temp_db):
        """Test indexes are created."""
        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            indexes = [row[0] for row in cursor.fetchall()]

        assert "idx_cluster_buys_ticker" in indexes
        assert "idx_cluster_buys_trade_date" in indexes
        assert "idx_cluster_buys_filing_date" in indexes

    def test_view_created(self, temp_db):
        """Test recent_clusters view is created."""
        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
            views = [row[0] for row in cursor.fetchall()]

        assert "recent_clusters" in views


class TestUpsertClusterBuy:
    """Tests for upsert_cluster_buy method."""

    def test_insert_new_cluster(self, temp_db, sample_cluster_buy):
        """Test inserting new cluster buy."""
        result = temp_db.upsert_cluster_buy(sample_cluster_buy)

        assert result == "inserted"

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cluster_buys")
            count = cursor.fetchone()[0]

        assert count == 1

    def test_insert_duplicate_returns_unchanged(self, temp_db, sample_cluster_buy):
        """Test inserting exact duplicate returns unchanged."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)
        result = temp_db.upsert_cluster_buy(sample_cluster_buy)

        assert result == "unchanged"

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cluster_buys")
            count = cursor.fetchone()[0]

        assert count == 1

    def test_update_when_insider_count_increases(self, temp_db, sample_cluster_buy):
        """Test updating when insider count increases."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        updated_cluster = ClusterBuy(
            ticker=sample_cluster_buy.ticker,
            company_name=sample_cluster_buy.company_name,
            industry=sample_cluster_buy.industry,
            insider_count=7,
            filing_date=sample_cluster_buy.filing_date,
            trade_date=sample_cluster_buy.trade_date,
            trade_type=sample_cluster_buy.trade_type,
            avg_price=Decimal("45.00"),
            total_qty=50000,
            total_value=2250000,
        )

        result = temp_db.upsert_cluster_buy(updated_cluster)

        assert result == "updated"

        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT insider_count, total_qty, total_value FROM cluster_buys WHERE ticker = ?",
                (sample_cluster_buy.ticker,),
            )
            row = cursor.fetchone()

        assert row[0] == 7
        assert row[1] == 50000
        assert row[2] == 2250000

    def test_no_update_when_insider_count_same(self, temp_db, sample_cluster_buy):
        """Test no update when insider count is same."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        same_cluster = ClusterBuy(
            ticker=sample_cluster_buy.ticker,
            company_name=sample_cluster_buy.company_name,
            industry=sample_cluster_buy.industry,
            insider_count=sample_cluster_buy.insider_count,
            filing_date=sample_cluster_buy.filing_date,
            trade_date=sample_cluster_buy.trade_date,
            trade_type=sample_cluster_buy.trade_type,
            total_qty=99999,
        )

        temp_db.upsert_cluster_buy(same_cluster)

        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT total_qty FROM cluster_buys WHERE ticker = ?",
                (sample_cluster_buy.ticker,),
            )
            row = cursor.fetchone()

        assert row[0] == sample_cluster_buy.total_qty

    def test_different_trade_date_creates_new_record(self, temp_db, sample_cluster_buy):
        """Test different trade date creates separate record."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        different_date = ClusterBuy(
            ticker=sample_cluster_buy.ticker,
            company_name=sample_cluster_buy.company_name,
            industry=sample_cluster_buy.industry,
            insider_count=sample_cluster_buy.insider_count,
            filing_date=sample_cluster_buy.filing_date,
            trade_date=date(2026, 1, 26),
            trade_type=sample_cluster_buy.trade_type,
        )

        result = temp_db.upsert_cluster_buy(different_date)

        assert result == "inserted"

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cluster_buys")
            count = cursor.fetchone()[0]

        assert count == 2

    def test_unique_constraint_prevents_duplicates(self, temp_db, sample_cluster_buy):
        """Test unique constraint on (ticker, trade_date, filing_date)."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cluster_buys")
            count = cursor.fetchone()[0]

        assert count == 1


class TestQueryMethods:
    """Tests for query methods."""

    def test_get_recent_clusters(self, temp_db, sample_cluster_buy):
        """Test getting recent clusters."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        clusters = temp_db.get_recent_clusters(limit=10)

        assert len(clusters) == 1
        assert clusters[0]["ticker"] == "AAPL"

    def test_get_recent_clusters_limit(self, temp_db):
        """Test limit parameter works."""
        for i in range(5):
            cluster = ClusterBuy(
                ticker=f"TST{i}",
                insider_count=1,
                filing_date=datetime.now(),
                trade_date=date.today(),
                trade_type="P",
            )
            temp_db.upsert_cluster_buy(cluster)

        clusters = temp_db.get_recent_clusters(limit=3)

        assert len(clusters) == 3

    def test_get_cluster_by_ticker(self, temp_db, sample_cluster_buy):
        """Test getting clusters by ticker."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        clusters = temp_db.get_cluster_by_ticker("AAPL", days=30)

        assert len(clusters) == 1
        assert clusters[0]["ticker"] == "AAPL"

    def test_get_cluster_by_ticker_case_insensitive(self, temp_db, sample_cluster_buy):
        """Test ticker search is case-insensitive."""
        temp_db.upsert_cluster_buy(sample_cluster_buy)

        clusters = temp_db.get_cluster_by_ticker("aapl", days=30)

        assert len(clusters) == 1

    def test_get_cluster_by_ticker_empty(self, temp_db):
        """Test getting clusters for non-existent ticker."""
        clusters = temp_db.get_cluster_by_ticker("NONEXIST", days=30)

        assert len(clusters) == 0


class TestScrapeLog:
    """Tests for scrape log operations."""

    def test_save_scrape_log(self, temp_db):
        """Test saving scrape log."""
        log = ScrapeLog(
            scrape_type="cluster_table",
            records_found=100,
            records_new=10,
            records_updated=5,
            duration_seconds=Decimal("12.34"),
            status="SUCCESS",
        )

        temp_db.save_scrape_log(log)

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM scrape_log")
            count = cursor.fetchone()[0]

        assert count == 1

    def test_save_scrape_log_with_error(self, temp_db):
        """Test saving failed scrape log with error message."""
        log = ScrapeLog(
            scrape_type="cluster_table",
            status="FAILED",
            error_message="Connection timeout",
        )

        temp_db.save_scrape_log(log)

        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status, error_message FROM scrape_log"
            )
            row = cursor.fetchone()

        assert row[0] == "FAILED"
        assert row[1] == "Connection timeout"

    def test_get_scrape_stats(self, temp_db):
        """Test getting scrape statistics."""
        for i in range(5):
            log = ScrapeLog(
                scrape_type="cluster_table",
                records_found=i * 10,
                status="SUCCESS",
            )
            temp_db.save_scrape_log(log)

        stats = temp_db.get_scrape_stats(limit=3)

        assert len(stats) == 3
        assert stats[0]["records_found"] == 40

    def test_get_scrape_stats_empty(self, temp_db):
        """Test getting stats when no logs exist."""
        stats = temp_db.get_scrape_stats(limit=10)

        assert len(stats) == 0
