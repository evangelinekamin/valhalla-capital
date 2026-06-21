"""SQLite database operations."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from openinsider.config import CONFIG
from openinsider.models import ClusterBuy, ScrapeLog, classify_insider_type

logger = logging.getLogger(__name__)


class OpenInsiderDB:
    """Database interface for OpenInsider data."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection."""
        self.db_path = db_path or CONFIG["database"]["path"]
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Create database and tables if they don't exist."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        schema_path = Path(CONFIG["database"]["schema_path"])
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with self._get_connection() as conn:
            with open(schema_path) as f:
                conn.executescript(f.read())
            conn.commit()

        logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def upsert_cluster_buy(self, cluster: ClusterBuy) -> str:
        """
        Insert or update cluster buy.

        Returns:
            "inserted" if new record, "updated" if existing record was updated,
            "unchanged" if existing record needed no update.
        """
        with self._get_connection() as conn:
            existing = conn.execute(
                """
                SELECT id, insider_count
                FROM cluster_buys
                WHERE ticker = ? AND trade_date = ? AND filing_date = ?
                """,
                (cluster.ticker, cluster.trade_date.isoformat(), cluster.filing_date.isoformat()),
            ).fetchone()

            if existing is None:
                self._insert_cluster_buy(conn, cluster)
                conn.commit()
                logger.debug(f"Inserted new cluster buy: {cluster.ticker} on {cluster.trade_date}")
                return "inserted"

            if cluster.insider_count > existing["insider_count"]:
                self._update_cluster_buy(conn, cluster, existing["id"])
                conn.commit()
                logger.debug(
                    f"Updated cluster buy: {cluster.ticker} on {cluster.trade_date} "
                    f"(insiders: {existing['insider_count']} -> {cluster.insider_count})"
                )
                return "updated"

            return "unchanged"

    def _insert_cluster_buy(self, conn: sqlite3.Connection, cluster: ClusterBuy) -> None:
        """Insert new cluster buy record."""
        conn.execute(
            """
            INSERT INTO cluster_buys (
                ticker, company_name, industry, insider_count,
                filing_date, trade_date, trade_type,
                avg_price, total_qty, total_owned, ownership_change_pct,
                total_value, transaction_code,
                perf_1d, perf_1w, perf_1m, perf_6m,
                source_url, first_seen_at, last_updated_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cluster.ticker,
                cluster.company_name,
                cluster.industry,
                cluster.insider_count,
                cluster.filing_date.isoformat(),
                cluster.trade_date.isoformat(),
                cluster.trade_type,
                str(cluster.avg_price) if cluster.avg_price else None,
                cluster.total_qty,
                cluster.total_owned,
                cluster.ownership_change_pct,
                cluster.total_value,
                cluster.transaction_code,
                str(cluster.perf_1d) if cluster.perf_1d else None,
                str(cluster.perf_1w) if cluster.perf_1w else None,
                str(cluster.perf_1m) if cluster.perf_1m else None,
                str(cluster.perf_6m) if cluster.perf_6m else None,
                cluster.source_url,
                cluster.first_seen_at.isoformat(),
                cluster.last_updated_at.isoformat(),
                cluster.is_active,
            ),
        )

    def _update_cluster_buy(self, conn: sqlite3.Connection, cluster: ClusterBuy, record_id: int) -> None:
        """Update existing cluster buy record."""
        conn.execute(
            """
            UPDATE cluster_buys
            SET
                insider_count = ?,
                total_qty = ?,
                total_value = ?,
                ownership_change_pct = ?,
                last_updated_at = ?
            WHERE id = ?
            """,
            (
                cluster.insider_count,
                cluster.total_qty,
                cluster.total_value,
                cluster.ownership_change_pct,
                cluster.last_updated_at.isoformat(),
                record_id,
            ),
        )

    def get_recent_clusters(self, limit: int = 100) -> List[dict]:
        """Get recent cluster buys."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM recent_clusters
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    def get_cluster_by_ticker(self, ticker: str, days: int = 30) -> List[dict]:
        """Get cluster buys for a specific ticker."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM cluster_buys
                WHERE ticker = ?
                AND trade_date >= date('now', ? || ' days')
                ORDER BY trade_date DESC
                """,
                (ticker.upper(), f"-{days}"),
            ).fetchall()

            return [dict(row) for row in rows]

    def save_scrape_log(self, log: ScrapeLog) -> None:
        """Save scrape execution log."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO scrape_log (
                    scrape_timestamp, scrape_type, records_found,
                    records_new, records_updated, duration_seconds,
                    status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.scrape_timestamp.isoformat(),
                    log.scrape_type,
                    log.records_found,
                    log.records_new,
                    log.records_updated,
                    str(log.duration_seconds) if log.duration_seconds else None,
                    log.status,
                    log.error_message,
                ),
            )
            conn.commit()

        logger.info(f"Saved scrape log: {log.status} - {log.records_new} new, {log.records_updated} updated")

    def get_scrape_stats(self, limit: int = 10) -> List[dict]:
        """Get recent scrape statistics."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM scrape_log
                ORDER BY scrape_timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    def save_insider_transaction(self, txn_data: dict, cluster_buy_id: Optional[int] = None) -> bool:
        """
        Insert insider transaction.

        Args:
            txn_data: Transaction data dictionary
            cluster_buy_id: Optional FK to cluster_buys table

        Returns:
            True if new record inserted, False if duplicate
        """
        with self._get_connection() as conn:
            existing = conn.execute(
                """
                SELECT id FROM insider_transactions
                WHERE ticker = ? AND insider_name = ? AND trade_date = ? AND trade_type = ?
                """,
                (
                    txn_data["ticker"],
                    txn_data["insider_name"],
                    txn_data["trade_date"].isoformat() if hasattr(txn_data["trade_date"], "isoformat") else txn_data["trade_date"],
                    txn_data["trade_type"],
                ),
            ).fetchone()

            if existing:
                return False

            insider_type = classify_insider_type(txn_data.get("insider_title", ""))

            conn.execute(
                """
                INSERT INTO insider_transactions (
                    cluster_buy_id, ticker, insider_name, insider_title, insider_type,
                    trade_date, trade_type, price, qty, owned_after,
                    ownership_change_pct, value, form_type, sec_link
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_buy_id,
                    txn_data["ticker"],
                    txn_data["insider_name"],
                    txn_data.get("insider_title"),
                    insider_type,
                    txn_data["trade_date"].isoformat() if hasattr(txn_data["trade_date"], "isoformat") else txn_data["trade_date"],
                    txn_data["trade_type"],
                    str(txn_data["price"]) if txn_data.get("price") else None,
                    txn_data.get("qty"),
                    txn_data.get("owned_after"),
                    str(txn_data["ownership_change_pct"]) if txn_data.get("ownership_change_pct") else None,
                    txn_data.get("value"),
                    txn_data.get("form_type"),
                    txn_data.get("sec_link"),
                ),
            )
            conn.commit()

            logger.debug(f"Inserted insider transaction: {txn_data['insider_name']} - {txn_data['ticker']}")
            return True

    def get_insider_transactions(self, ticker: str, days: int = 30) -> List[dict]:
        """Get insider transactions for a specific ticker."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM insider_transactions
                WHERE ticker = ?
                AND trade_date >= date('now', ? || ' days')
                ORDER BY trade_date DESC
                """,
                (ticker.upper(), f"-{days}"),
            ).fetchall()

            return [dict(row) for row in rows]

    def get_executive_transactions(self, days: int = 30) -> List[dict]:
        """Get executive-only transactions."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM insider_transactions
                WHERE insider_type = 'executive'
                AND trade_date >= date('now', ? || ' days')
                ORDER BY trade_date DESC, value DESC
                """,
                (f"-{days}",),
            ).fetchall()

            return [dict(row) for row in rows]
