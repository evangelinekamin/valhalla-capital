"""Integration tests for end-to-end workflows."""

import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from openinsider.database import OpenInsiderDB
from openinsider.models import ClusterBuy
from openinsider.scraper import OpenInsiderScraper


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_scrape_and_save_workflow(self, mocker, sample_html_table):
        """Test complete workflow: scrape -> parse -> save -> query."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            mock_response = mocker.Mock()
            mock_response.text = sample_html_table
            mock_response.status_code = 200
            mocker.patch("requests.Session.get", return_value=mock_response)

            db = OpenInsiderDB(db_path)

            with OpenInsiderScraper() as scraper:
                clusters = scraper.scrape_cluster_buys()

                assert len(clusters) == 2

                new_count = 0
                for cluster in clusters:
                    result = db.upsert_cluster_buy(cluster)
                    if result == "inserted":
                        new_count += 1

                assert new_count == 2

            recent = db.get_recent_clusters(limit=10)
            assert len(recent) == 2

            aapl_clusters = db.get_cluster_by_ticker("AAPL", days=30)
            assert len(aapl_clusters) == 1
            assert aapl_clusters[0]["insider_count"] == 5

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_rescrape_and_update_workflow(self, mocker, sample_html_table):
        """Test re-scraping updates existing records correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            mock_response = mocker.Mock()
            mock_response.text = sample_html_table
            mock_response.status_code = 200
            mocker.patch("requests.Session.get", return_value=mock_response)

            db = OpenInsiderDB(db_path)

            with OpenInsiderScraper() as scraper:
                clusters1 = scraper.scrape_cluster_buys()
                for cluster in clusters1:
                    db.upsert_cluster_buy(cluster)

                clusters2 = scraper.scrape_cluster_buys()
                new_count = 0
                for cluster in clusters2:
                    result = db.upsert_cluster_buy(cluster)
                    if result == "inserted":
                        new_count += 1

                assert new_count == 0

            with db._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM cluster_buys")
                count = cursor.fetchone()[0]

            assert count == 2

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_insider_count_increase_update(self):
        """Test updating when more insiders join a cluster."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            db = OpenInsiderDB(db_path)

            initial_cluster = ClusterBuy(
                ticker="AAPL",
                company_name="Apple Inc.",
                insider_count=3,
                filing_date=datetime(2026, 1, 28, 16, 0, 0),
                trade_date=date(2026, 1, 27),
                trade_type="P",
                total_qty=10000,
                total_value=500000,
            )

            result = db.upsert_cluster_buy(initial_cluster)
            assert result == "inserted"

            updated_cluster = ClusterBuy(
                ticker="AAPL",
                company_name="Apple Inc.",
                insider_count=5,
                filing_date=datetime(2026, 1, 28, 16, 0, 0),
                trade_date=date(2026, 1, 27),
                trade_type="P",
                total_qty=20000,
                total_value=1000000,
            )

            result = db.upsert_cluster_buy(updated_cluster)
            assert result == "updated"

            clusters = db.get_cluster_by_ticker("AAPL", days=30)
            assert len(clusters) == 1
            assert clusters[0]["insider_count"] == 5
            assert clusters[0]["total_qty"] == 20000
            assert clusters[0]["total_value"] == 1000000

        finally:
            Path(db_path).unlink(missing_ok=True)
