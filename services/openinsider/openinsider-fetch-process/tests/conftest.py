"""Pytest configuration and fixtures."""

import sqlite3
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from openinsider.config import CONFIG
from openinsider.database import OpenInsiderDB
from openinsider.models import ClusterBuy


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = OpenInsiderDB(db_path)
    yield db

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_cluster_buy():
    """Create sample ClusterBuy for testing."""
    return ClusterBuy(
        ticker="AAPL",
        company_name="Apple Inc.",
        industry="Technology",
        insider_count=5,
        filing_date=datetime(2026, 1, 28, 16, 48, 14),
        trade_date=date(2026, 1, 27),
        trade_type="P - Purchase",
        avg_price=Decimal("42.16"),
        total_qty=35366,
        total_owned=100000,
        ownership_change_pct="+54.7%",
        total_value=1491174,
        transaction_code="P",
        perf_1d=Decimal("1.23"),
        perf_1w=Decimal("2.45"),
        perf_1m=Decimal("5.67"),
        perf_6m=Decimal("12.34"),
        source_url="http://openinsider.com/latest-cluster-buys",
    )


@pytest.fixture
def sample_html_table():
    """Sample HTML table for parser testing."""
    return """
    <table class="tinytable">
        <thead>
            <tr>
                <th>X</th>
                <th>Filing Date</th>
                <th>Trade Date</th>
                <th>Ticker</th>
                <th>Company Name</th>
                <th>Industry</th>
                <th>Ins</th>
                <th>Trade Type</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Owned</th>
                <th>ΔOwn</th>
                <th>Value</th>
                <th>Code</th>
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
                <td>Apple Inc.</td>
                <td>Technology</td>
                <td>5</td>
                <td>P - Purchase</td>
                <td>$42.16</td>
                <td>+35,366</td>
                <td>100,000</td>
                <td>+54.7%</td>
                <td>+$1,491,174</td>
                <td>P</td>
                <td>+1.23%</td>
                <td>+2.45%</td>
                <td>+5.67%</td>
                <td>+12.34%</td>
            </tr>
            <tr>
                <td><input type="checkbox"></td>
                <td>2026-01-28 15:30:00</td>
                <td>2026-01-27</td>
                <td>MSFT</td>
                <td>Microsoft Corporation</td>
                <td>Technology</td>
                <td>3</td>
                <td>P - Purchase</td>
                <td>$310.50</td>
                <td>+10,000</td>
                <td>50,000</td>
                <td>+25.0%</td>
                <td>+$3,105,000</td>
                <td>P</td>
                <td>-0.5%</td>
                <td>+1.2%</td>
                <td>+3.4%</td>
                <td>+8.9%</td>
            </tr>
        </tbody>
    </table>
    """


@pytest.fixture
def sample_html_edge_cases():
    """Sample HTML with edge cases (missing data, unusual formats)."""
    return """
    <table class="tinytable">
        <thead>
            <tr>
                <th>X</th>
                <th>Filing Date</th>
                <th>Trade Date</th>
                <th>Ticker</th>
                <th>Company Name</th>
                <th>Industry</th>
                <th>Ins</th>
                <th>Trade Type</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Owned</th>
                <th>ΔOwn</th>
                <th>Value</th>
                <th>Code</th>
                <th>1d</th>
                <th>1w</th>
                <th>1m</th>
                <th>6m</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><input type="checkbox"></td>
                <td>2026-01-28 16:00:00</td>
                <td>2026-01-27</td>
                <td>TEST</td>
                <td>Test Company</td>
                <td>-</td>
                <td>1</td>
                <td>P - Purchase</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
                <td>>999%</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
            </tr>
        </tbody>
    </table>
    """
