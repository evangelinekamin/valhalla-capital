"""Tests for HTML parser."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from openinsider.parser import (
    _parse_date,
    _parse_datetime,
    _parse_int,
    _parse_percent,
    _parse_price,
    _parse_qty,
    _parse_value,
    parse_cluster_table,
)


class TestParseHelpers:
    """Tests for parsing helper functions."""

    def test_parse_datetime_valid(self):
        """Test parsing valid datetime string."""
        result = _parse_datetime("2026-01-28 16:48:14")
        assert result == datetime(2026, 1, 28, 16, 48, 14)

    def test_parse_datetime_date_only(self):
        """Test parsing date-only string falls back to date parsing."""
        result = _parse_datetime("2026-01-28")
        assert result.date() == date(2026, 1, 28)

    def test_parse_datetime_empty(self):
        """Test parsing empty string returns current time."""
        result = _parse_datetime("")
        assert isinstance(result, datetime)

    def test_parse_date_valid(self):
        """Test parsing valid date string."""
        result = _parse_date("2026-01-27")
        assert result == date(2026, 1, 27)

    def test_parse_date_empty(self):
        """Test parsing empty string returns today."""
        result = _parse_date("")
        assert result == date.today()

    def test_parse_price_with_dollar_sign(self):
        """Test parsing price with dollar sign."""
        result = _parse_price("$42.16")
        assert result == Decimal("42.16")

    def test_parse_price_with_commas(self):
        """Test parsing price with commas."""
        result = _parse_price("$1,234.56")
        assert result == Decimal("1234.56")

    def test_parse_price_dash(self):
        """Test parsing dash returns None."""
        result = _parse_price("-")
        assert result is None

    def test_parse_price_empty(self):
        """Test parsing empty string returns None."""
        result = _parse_price("")
        assert result is None

    def test_parse_qty_with_plus_and_commas(self):
        """Test parsing quantity with + and commas."""
        result = _parse_qty("+35,366")
        assert result == 35366

    def test_parse_qty_negative(self):
        """Test parsing negative quantity."""
        result = _parse_qty("-10,000")
        assert result == 10000

    def test_parse_qty_dash(self):
        """Test parsing dash returns None."""
        result = _parse_qty("-")
        assert result is None

    def test_parse_value_with_dollar_and_commas(self):
        """Test parsing value with $ and commas."""
        result = _parse_value("+$1,491,174")
        assert result == 1491174

    def test_parse_value_millions(self):
        """Test parsing large value."""
        result = _parse_value("$10,000,000")
        assert result == 10000000

    def test_parse_value_dash(self):
        """Test parsing dash returns None."""
        result = _parse_value("-")
        assert result is None

    def test_parse_percent_with_plus(self):
        """Test parsing percentage with + sign."""
        result = _parse_percent("+5.23%")
        assert result == Decimal("5.23")

    def test_parse_percent_negative(self):
        """Test parsing negative percentage."""
        result = _parse_percent("-3.45%")
        assert result == Decimal("-3.45")

    def test_parse_percent_dash(self):
        """Test parsing dash returns None."""
        result = _parse_percent("-")
        assert result is None

    def test_parse_int_valid(self):
        """Test parsing valid integer."""
        result = _parse_int("42")
        assert result == 42

    def test_parse_int_invalid(self):
        """Test parsing invalid integer returns None."""
        result = _parse_int("abc")
        assert result is None


class TestParseClusterTable:
    """Tests for parse_cluster_table function."""

    def test_parse_valid_table(self, sample_html_table):
        """Test parsing valid HTML table."""
        clusters = parse_cluster_table(sample_html_table, "http://test.com")

        assert len(clusters) == 2

        cluster1 = clusters[0]
        assert cluster1.ticker == "AAPL"
        assert cluster1.company_name == "Apple Inc."
        assert cluster1.industry == "Technology"
        assert cluster1.insider_count == 5
        assert cluster1.trade_type == "P - Purchase"
        assert cluster1.avg_price == Decimal("42.16")
        assert cluster1.total_qty == 35366
        assert cluster1.total_value == 1491174
        assert cluster1.ownership_change_pct == "+54.7%"
        assert cluster1.source_url == "http://test.com"

        cluster2 = clusters[1]
        assert cluster2.ticker == "MSFT"
        assert cluster2.company_name == "Microsoft Corporation"
        assert cluster2.insider_count == 3

    def test_parse_edge_cases(self, sample_html_edge_cases):
        """Test parsing HTML with missing/unusual data."""
        clusters = parse_cluster_table(sample_html_edge_cases)

        assert len(clusters) == 1

        cluster = clusters[0]
        assert cluster.ticker == "TEST"
        assert cluster.company_name == "Test Company"
        assert cluster.insider_count == 1
        assert cluster.ownership_change_pct == ">999%"
        assert cluster.avg_price is None
        assert cluster.total_qty is None
        assert cluster.total_value is None

    def test_parse_no_table(self):
        """Test parsing HTML with no table returns empty list."""
        html = "<html><body><p>No table here</p></body></html>"
        clusters = parse_cluster_table(html)
        assert clusters == []

    def test_parse_empty_table(self):
        """Test parsing empty table returns empty list."""
        html = """
        <table class="tinytable">
            <thead><tr><th>Header</th></tr></thead>
            <tbody></tbody>
        </table>
        """
        clusters = parse_cluster_table(html)
        assert clusters == []

    def test_parse_malformed_row(self):
        """Test parsing table with malformed row skips it."""
        html = """
        <table class="tinytable">
            <thead><tr><th>Header</th></tr></thead>
            <tbody>
                <tr>
                    <td>Only</td>
                    <td>Three</td>
                    <td>Cells</td>
                </tr>
            </tbody>
        </table>
        """
        clusters = parse_cluster_table(html)
        assert clusters == []

    def test_parse_performance_metrics(self, sample_html_table):
        """Test parsing performance metrics correctly."""
        clusters = parse_cluster_table(sample_html_table)

        cluster1 = clusters[0]
        assert cluster1.perf_1d == Decimal("1.23")
        assert cluster1.perf_1w == Decimal("2.45")
        assert cluster1.perf_1m == Decimal("5.67")
        assert cluster1.perf_6m == Decimal("12.34")

        cluster2 = clusters[1]
        assert cluster2.perf_1d == Decimal("-0.5")
        assert cluster2.perf_1w == Decimal("1.2")

    def test_parse_dates(self, sample_html_table):
        """Test parsing filing and trade dates."""
        clusters = parse_cluster_table(sample_html_table)

        cluster = clusters[0]
        assert cluster.filing_date == datetime(2026, 1, 28, 16, 48, 14)
        assert cluster.trade_date == date(2026, 1, 27)
