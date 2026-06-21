"""Tests for Pydantic models."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from openinsider.models import ClusterBuy, InsiderTransaction, ScrapeLog


class TestClusterBuy:
    """Tests for ClusterBuy model."""

    def test_valid_cluster_buy(self, sample_cluster_buy):
        """Test creating valid ClusterBuy."""
        assert sample_cluster_buy.ticker == "AAPL"
        assert sample_cluster_buy.company_name == "Apple Inc."
        assert sample_cluster_buy.insider_count == 5
        assert sample_cluster_buy.avg_price == Decimal("42.16")

    def test_ticker_uppercase_conversion(self):
        """Test ticker is automatically converted to uppercase."""
        cluster = ClusterBuy(
            ticker="aapl",
            insider_count=5,
            filing_date=datetime.now(),
            trade_date=date.today(),
            trade_type="P",
        )
        assert cluster.ticker == "AAPL"

    def test_ticker_strip_whitespace(self):
        """Test ticker whitespace is stripped."""
        cluster = ClusterBuy(
            ticker="  AAPL  ",
            insider_count=5,
            filing_date=datetime.now(),
            trade_date=date.today(),
            trade_type="P",
        )
        assert cluster.ticker == "AAPL"

    def test_insider_count_minimum_validation(self):
        """Test insider count must be at least 1."""
        with pytest.raises(ValidationError):
            ClusterBuy(
                ticker="AAPL",
                insider_count=0,
                filing_date=datetime.now(),
                trade_date=date.today(),
                trade_type="P",
            )

    def test_ownership_change_special_format(self):
        """Test >999% ownership change is allowed."""
        cluster = ClusterBuy(
            ticker="AAPL",
            insider_count=5,
            filing_date=datetime.now(),
            trade_date=date.today(),
            trade_type="P",
            ownership_change_pct=">999%",
        )
        assert cluster.ownership_change_pct == ">999%"

    def test_immutability(self, sample_cluster_buy):
        """Test ClusterBuy is immutable (frozen)."""
        with pytest.raises(ValidationError):
            sample_cluster_buy.ticker = "MSFT"

    def test_optional_fields_none(self):
        """Test optional fields can be None."""
        cluster = ClusterBuy(
            ticker="AAPL",
            insider_count=5,
            filing_date=datetime.now(),
            trade_date=date.today(),
            trade_type="P",
            avg_price=None,
            total_qty=None,
            company_name=None,
        )
        assert cluster.avg_price is None
        assert cluster.total_qty is None
        assert cluster.company_name is None

    def test_default_timestamps(self):
        """Test default timestamps are set."""
        cluster = ClusterBuy(
            ticker="AAPL",
            insider_count=5,
            filing_date=datetime.now(),
            trade_date=date.today(),
            trade_type="P",
        )
        assert cluster.first_seen_at is not None
        assert cluster.last_updated_at is not None
        assert cluster.is_active is True


class TestInsiderTransaction:
    """Tests for InsiderTransaction model."""

    def test_valid_insider_transaction(self):
        """Test creating valid InsiderTransaction."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            insider_title="CEO",
            insider_type="executive",
            trade_date=date.today(),
            trade_type="P",
        )
        assert txn.ticker == "AAPL"
        assert txn.insider_name == "John Doe"
        assert txn.insider_type == "executive"

    def test_classify_executive(self):
        """Test CEO/CFO titles are classified as executive."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            insider_title="Chief Executive Officer",
            insider_type="unknown",
            trade_date=date.today(),
            trade_type="P",
        )
        assert txn.insider_type == "executive"

    def test_classify_cfo(self):
        """Test CFO title is classified as executive."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="Jane Smith",
            insider_title="Chief Financial Officer",
            insider_type="unknown",
            trade_date=date.today(),
            trade_type="P",
        )
        assert txn.insider_type == "executive"

    def test_classify_fund(self):
        """Test fund/10% owner titles are classified as fund."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="Investment Fund LLC",
            insider_title="10% Owner",
            insider_type="unknown",
            trade_date=date.today(),
            trade_type="P",
        )
        assert txn.insider_type == "fund"

    def test_classify_director(self):
        """Test director title is classified correctly."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="Bob Director",
            insider_title="Director",
            insider_type="unknown",
            trade_date=date.today(),
            trade_type="P",
        )
        assert txn.insider_type == "director"

    def test_classify_other(self):
        """Test unknown title is classified as other."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="Unknown Person",
            insider_title="Some Random Title",
            insider_type="unknown",
            trade_date=date.today(),
            trade_type="P",
        )
        assert txn.insider_type == "other"

    def test_immutability(self):
        """Test InsiderTransaction is immutable."""
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            insider_type="executive",
            trade_date=date.today(),
            trade_type="P",
        )
        with pytest.raises(ValidationError):
            txn.ticker = "MSFT"


class TestScrapeLog:
    """Tests for ScrapeLog model."""

    def test_valid_scrape_log(self):
        """Test creating valid ScrapeLog."""
        log = ScrapeLog(
            scrape_type="cluster_table",
            records_found=100,
            records_new=10,
            records_updated=5,
            duration_seconds=Decimal("12.34"),
            status="SUCCESS",
        )
        assert log.scrape_type == "cluster_table"
        assert log.records_found == 100
        assert log.status == "SUCCESS"

    def test_status_validation_uppercase(self):
        """Test status is converted to uppercase."""
        log = ScrapeLog(
            scrape_type="test",
            status="success",
        )
        assert log.status == "SUCCESS"

    def test_status_validation_invalid(self):
        """Test invalid status raises error."""
        with pytest.raises(ValidationError):
            ScrapeLog(
                scrape_type="test",
                status="INVALID",
            )

    def test_status_allowed_values(self):
        """Test all allowed status values work."""
        for status in ["SUCCESS", "PARTIAL", "FAILED"]:
            log = ScrapeLog(scrape_type="test", status=status)
            assert log.status == status

    def test_default_values(self):
        """Test default values are set."""
        log = ScrapeLog(scrape_type="test", status="SUCCESS")
        assert log.scrape_timestamp is not None
        assert log.records_found == 0
        assert log.records_new == 0
        assert log.records_updated == 0

    def test_optional_error_message(self):
        """Test error message can be set."""
        log = ScrapeLog(
            scrape_type="test",
            status="FAILED",
            error_message="Connection timeout",
        )
        assert log.error_message == "Connection timeout"

    def test_immutability(self):
        """Test ScrapeLog is immutable."""
        log = ScrapeLog(scrape_type="test", status="SUCCESS")
        with pytest.raises(ValidationError):
            log.status = "FAILED"
