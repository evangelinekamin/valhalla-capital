"""Tests for Phase 2 - Individual insider details."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from openinsider.parser import parse_insider_detail_page


@pytest.fixture
def sample_insider_html():
    """Sample HTML from ticker detail page."""
    return """
    <table class="tinytable">
        <thead>
            <tr>
                <th>X</th>
                <th>Filing Date</th>
                <th>Trade Date</th>
                <th>Ticker</th>
                <th>Insider Name</th>
                <th>Title</th>
                <th>Trade Type</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Owned</th>
                <th>ΔOwn</th>
                <th>Value</th>
                <th>1d</th>
                <th>1w</th>
                <th>1m</th>
                <th>6m</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><input type="checkbox"></td>
                <td>2026-01-28 16:48:14</td>
                <td>2026-01-27</td>
                <td>AAPL</td>
                <td>John Doe</td>
                <td>CEO</td>
                <td>P - Purchase</td>
                <td>$43.17</td>
                <td>+11,566</td>
                <td>231,336</td>
                <td>+5%</td>
                <td>+$499,307</td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
            </tr>
            <tr>
                <td><input type="checkbox"></td>
                <td>2026-01-23 16:19:05</td>
                <td>2026-01-23</td>
                <td>AAPL</td>
                <td>Jane Smith</td>
                <td>CFO</td>
                <td>S - Sale</td>
                <td>$42.50</td>
                <td>-5,000</td>
                <td>50,000</td>
                <td>-10%</td>
                <td>-$212,500</td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
            </tr>
            <tr>
                <td><input type="checkbox"></td>
                <td>2026-01-20 10:00:00</td>
                <td>2026-01-19</td>
                <td>AAPL</td>
                <td>Investment Fund LLC</td>
                <td>10% Owner</td>
                <td>P - Purchase</td>
                <td>$41.00</td>
                <td>+100,000</td>
                <td>1,000,000</td>
                <td>+11%</td>
                <td>+$4,100,000</td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
            </tr>
        </tbody>
    </table>
    """


class TestParseInsiderDetailPage:
    """Tests for parse_insider_detail_page function."""

    def test_parse_valid_insider_page(self, sample_insider_html):
        """Test parsing valid insider detail page."""
        transactions = parse_insider_detail_page(sample_insider_html, "AAPL")

        assert len(transactions) == 3

        txn1 = transactions[0]
        assert txn1["ticker"] == "AAPL"
        assert txn1["insider_name"] == "John Doe"
        assert txn1["insider_title"] == "CEO"
        assert txn1["trade_type"] == "P - Purchase"
        assert txn1["price"] == Decimal("43.17")
        assert txn1["qty"] == 11566
        assert txn1["owned_after"] == 231336
        assert txn1["value"] == 499307

    def test_parse_executive_title(self, sample_insider_html):
        """Test parsing executive (CEO) transaction."""
        transactions = parse_insider_detail_page(sample_insider_html, "AAPL")

        ceo_txn = transactions[0]
        assert ceo_txn["insider_title"] == "CEO"

    def test_parse_fund_transaction(self, sample_insider_html):
        """Test parsing fund (10% Owner) transaction."""
        transactions = parse_insider_detail_page(sample_insider_html, "AAPL")

        fund_txn = transactions[2]
        assert fund_txn["insider_name"] == "Investment Fund LLC"
        assert fund_txn["insider_title"] == "10% Owner"
        assert fund_txn["qty"] == 100000

    def test_parse_sale_transaction(self, sample_insider_html):
        """Test parsing sale transaction."""
        transactions = parse_insider_detail_page(sample_insider_html, "AAPL")

        sale_txn = transactions[1]
        assert sale_txn["trade_type"] == "S - Sale"
        assert sale_txn["insider_name"] == "Jane Smith"

    def test_parse_no_table(self):
        """Test parsing HTML with no table."""
        html = "<html><body><p>No table here</p></body></html>"
        transactions = parse_insider_detail_page(html, "AAPL")

        assert transactions == []

    def test_parse_empty_table(self):
        """Test parsing empty table."""
        html = """
        <table class="tinytable">
            <thead><tr><th>Header</th></tr></thead>
            <tbody></tbody>
        </table>
        """
        transactions = parse_insider_detail_page(html, "AAPL")

        assert transactions == []

    def test_ticker_uppercase_conversion(self, sample_insider_html):
        """Test ticker is converted to uppercase."""
        transactions = parse_insider_detail_page(sample_insider_html, "aapl")

        for txn in transactions:
            assert txn["ticker"] == "AAPL"


class TestDatabaseInsiderTransactions:
    """Tests for insider transaction database operations."""

    def test_save_insider_transaction(self, temp_db):
        """Test saving insider transaction."""
        txn_data = {
            "ticker": "AAPL",
            "insider_name": "John Doe",
            "insider_title": "CEO",
            "trade_date": date(2026, 1, 27),
            "trade_type": "P - Purchase",
            "price": Decimal("43.17"),
            "qty": 11566,
            "owned_after": 231336,
            "ownership_change_pct": Decimal("5.0"),
            "value": 499307,
        }

        is_new = temp_db.save_insider_transaction(txn_data)

        assert is_new is True

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM insider_transactions")
            count = cursor.fetchone()[0]

        assert count == 1

    def test_save_duplicate_transaction(self, temp_db):
        """Test saving duplicate transaction returns False."""
        txn_data = {
            "ticker": "AAPL",
            "insider_name": "John Doe",
            "insider_title": "CEO",
            "trade_date": date(2026, 1, 27),
            "trade_type": "P - Purchase",
        }

        temp_db.save_insider_transaction(txn_data)
        is_new = temp_db.save_insider_transaction(txn_data)

        assert is_new is False

    def test_classify_executive(self, temp_db):
        """Test CEO/CFO are classified as executive."""
        txn_data = {
            "ticker": "AAPL",
            "insider_name": "John Doe",
            "insider_title": "Chief Executive Officer",
            "trade_date": date(2026, 1, 27),
            "trade_type": "P",
        }

        temp_db.save_insider_transaction(txn_data)

        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT insider_type FROM insider_transactions WHERE insider_name = ?",
                ("John Doe",),
            )
            insider_type = cursor.fetchone()[0]

        assert insider_type == "executive"

    def test_classify_fund(self, temp_db):
        """Test 10% Owner is classified as fund."""
        txn_data = {
            "ticker": "AAPL",
            "insider_name": "Investment Fund LLC",
            "insider_title": "10% Owner",
            "trade_date": date(2026, 1, 27),
            "trade_type": "P",
        }

        temp_db.save_insider_transaction(txn_data)

        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT insider_type FROM insider_transactions WHERE insider_name = ?",
                ("Investment Fund LLC",),
            )
            insider_type = cursor.fetchone()[0]

        assert insider_type == "fund"

    def test_classify_director(self, temp_db):
        """Test Director is classified correctly."""
        txn_data = {
            "ticker": "AAPL",
            "insider_name": "Jane Director",
            "insider_title": "Director",
            "trade_date": date(2026, 1, 27),
            "trade_type": "P",
        }

        temp_db.save_insider_transaction(txn_data)

        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT insider_type FROM insider_transactions WHERE insider_name = ?",
                ("Jane Director",),
            )
            insider_type = cursor.fetchone()[0]

        assert insider_type == "director"

    def test_get_insider_transactions(self, temp_db):
        """Test querying insider transactions by ticker."""
        txn1 = {
            "ticker": "AAPL",
            "insider_name": "John Doe",
            "trade_date": date.today(),
            "trade_type": "P",
        }
        txn2 = {
            "ticker": "AAPL",
            "insider_name": "Jane Smith",
            "trade_date": date.today(),
            "trade_type": "S",
        }
        txn3 = {
            "ticker": "MSFT",
            "insider_name": "Bob Jones",
            "trade_date": date.today(),
            "trade_type": "P",
        }

        temp_db.save_insider_transaction(txn1)
        temp_db.save_insider_transaction(txn2)
        temp_db.save_insider_transaction(txn3)

        aapl_txns = temp_db.get_insider_transactions("AAPL", days=30)

        assert len(aapl_txns) == 2

    def test_get_executive_transactions(self, temp_db):
        """Test filtering executive-only transactions."""
        exec_txn = {
            "ticker": "AAPL",
            "insider_name": "John CEO",
            "insider_title": "CEO",
            "trade_date": date.today(),
            "trade_type": "P",
        }
        fund_txn = {
            "ticker": "AAPL",
            "insider_name": "Big Fund",
            "insider_title": "10% Owner",
            "trade_date": date.today(),
            "trade_type": "P",
        }

        temp_db.save_insider_transaction(exec_txn)
        temp_db.save_insider_transaction(fund_txn)

        execs = temp_db.get_executive_transactions(days=30)

        assert len(execs) == 1
        assert execs[0]["insider_type"] == "executive"
