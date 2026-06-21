"""HTML parser for OpenInsider data."""

import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from bs4 import BeautifulSoup

from openinsider.models import ClusterBuy

logger = logging.getLogger(__name__)


def parse_cluster_table(html: str, source_url: str = "") -> List[ClusterBuy]:
    """
    Extract cluster buys from main table HTML.

    Args:
        html: Raw HTML content
        source_url: Source URL for reference

    Returns:
        List of ClusterBuy objects
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tinytable")

    if not table:
        logger.warning("Could not find tinytable in HTML")
        return []

    tbody = table.find("tbody")
    if not tbody:
        logger.warning("Could not find tbody in table")
        return []

    clusters = []
    for row in tbody.find_all("tr"):
        try:
            cluster = _parse_table_row(row, source_url)
            if cluster:
                clusters.append(cluster)
        except Exception as e:
            logger.error(f"Failed to parse row: {e}", exc_info=True)
            continue

    logger.info(f"Parsed {len(clusters)} cluster buys from table")
    return clusters


def _parse_table_row(row, source_url: str) -> Optional[ClusterBuy]:
    """
    Parse a single table row into ClusterBuy model.

    Table structure (17 columns):
    0: X (checkbox)
    1: Filing Date
    2: Trade Date
    3: Ticker
    4: Company Name
    5: Industry
    6: Ins (insider count)
    7: Trade Type
    8: Price
    9: Qty
    10: Owned
    11: ΔOwn
    12: Value
    13: (unknown/transaction code)
    14-17: Performance (1d/1w/1m/6m)
    """
    cells = row.find_all("td")

    if len(cells) < 14:
        logger.debug(f"Row has {len(cells)} cells, skipping")
        return None

    ticker = _get_text(cells[3])
    if not ticker:
        return None

    return ClusterBuy(
        ticker=ticker,
        company_name=_get_text(cells[4]),
        industry=_get_text(cells[5]),
        insider_count=_parse_int(_get_text(cells[6])) or 1,
        filing_date=_parse_datetime(_get_text(cells[1])),
        trade_date=_parse_date(_get_text(cells[2])),
        trade_type=_get_text(cells[7]),
        avg_price=_parse_price(_get_text(cells[8])),
        total_qty=_parse_qty(_get_text(cells[9])),
        total_owned=_parse_qty(_get_text(cells[10])),
        ownership_change_pct=_get_text(cells[11]),
        total_value=_parse_value(_get_text(cells[12])),
        transaction_code=_get_text(cells[13]) if len(cells) > 13 else None,
        perf_1d=_parse_percent(_get_text(cells[14])) if len(cells) > 14 else None,
        perf_1w=_parse_percent(_get_text(cells[15])) if len(cells) > 15 else None,
        perf_1m=_parse_percent(_get_text(cells[16])) if len(cells) > 16 else None,
        perf_6m=_parse_percent(_get_text(cells[17])) if len(cells) > 17 else None,
        source_url=source_url,
    )


def _get_text(cell) -> str:
    """Extract text from cell, handling None."""
    if cell is None:
        return ""
    return cell.get_text(strip=True)


def _parse_datetime(s: str) -> datetime:
    """Parse datetime string: '2026-01-28 16:48:14'."""
    if not s:
        return datetime.now(timezone.utc)

    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Could not parse datetime: {s}")
            return datetime.now(timezone.utc)


def _parse_date(s: str) -> date:
    """Parse date string: '2026-01-27'."""
    if not s:
        return date.today()

    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"Could not parse date: {s}")
        return date.today()


def _parse_price(s: str) -> Optional[Decimal]:
    """Parse price string: '$42.16' -> 42.16."""
    if not s or s == "-":
        return None

    cleaned = re.sub(r"[^0-9.]", "", s)
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        logger.warning(f"Could not parse price: {s}")
        return None


def _parse_qty(s: str) -> Optional[int]:
    """Parse quantity string: '+35,366' -> 35366."""
    if not s or s == "-":
        return None

    cleaned = re.sub(r"[^0-9]", "", s)
    if not cleaned:
        return None

    try:
        return int(cleaned)
    except ValueError:
        logger.warning(f"Could not parse quantity: {s}")
        return None


def _parse_value(s: str) -> Optional[int]:
    """Parse value string: '+$1,491,174' -> 1491174."""
    if not s or s == "-":
        return None

    cleaned = re.sub(r"[^0-9]", "", s)
    if not cleaned:
        return None

    try:
        return int(cleaned)
    except ValueError:
        logger.warning(f"Could not parse value: {s}")
        return None


def _parse_percent(s: str) -> Optional[Decimal]:
    """Parse percentage string: '+5.23%' -> 5.23."""
    if not s or s == "-":
        return None

    cleaned = re.sub(r"[^0-9.\-+]", "", s)
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        logger.warning(f"Could not parse percentage: {s}")
        return None


def _parse_int(s: str) -> Optional[int]:
    """Parse integer string."""
    if not s or s == "-":
        return None

    try:
        return int(s)
    except ValueError:
        logger.warning(f"Could not parse integer: {s}")
        return None


def parse_insider_detail_page(html: str, ticker: str) -> List[dict]:
    """
    Extract individual insider transactions from ticker detail page.

    Args:
        html: Raw HTML content
        ticker: Stock ticker symbol

    Returns:
        List of insider transaction dictionaries
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tinytable")

    if not table:
        logger.warning("Could not find tinytable in ticker detail HTML")
        return []

    tbody = table.find("tbody")
    if not tbody:
        logger.warning("Could not find tbody in ticker detail table")
        return []

    transactions = []
    for row in tbody.find_all("tr"):
        try:
            txn = _parse_insider_row(row, ticker)
            if txn:
                transactions.append(txn)
        except Exception as e:
            logger.error(f"Failed to parse insider row: {e}", exc_info=True)
            continue

    logger.info(f"Parsed {len(transactions)} insider transactions for {ticker}")
    return transactions


def _parse_insider_row(row, ticker: str) -> Optional[dict]:
    """
    Parse a single insider transaction row.

    Table structure (16 columns):
    0: X (checkbox)
    1: Filing Date
    2: Trade Date
    3: Ticker
    4: Insider Name
    5: Title
    6: Trade Type
    7: Price
    8: Qty
    9: Owned
    10: ΔOwn
    11: Value
    12-15: Performance (1d/1w/1m/6m)
    """
    cells = row.find_all("td")

    if len(cells) < 12:
        logger.debug(f"Row has {len(cells)} cells, skipping")
        return None

    insider_name = _get_text(cells[4])
    if not insider_name:
        return None

    return {
        "ticker": ticker.upper(),
        "insider_name": insider_name,
        "insider_title": _get_text(cells[5]),
        "trade_date": _parse_date(_get_text(cells[2])),
        "trade_type": _get_text(cells[6]),
        "price": _parse_price(_get_text(cells[7])),
        "qty": _parse_qty(_get_text(cells[8])),
        "owned_after": _parse_qty(_get_text(cells[9])),
        "ownership_change_pct": _parse_percent(_get_text(cells[10])),
        "value": _parse_value(_get_text(cells[11])),
    }
