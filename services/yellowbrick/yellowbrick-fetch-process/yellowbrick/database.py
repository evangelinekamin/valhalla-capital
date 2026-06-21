"""
Database layer for Yellowbrick scraper.

Provides SQLite storage for pitch data with:
- Upsert logic (insert new, update existing)
- Query helpers for recent pitches
- Scrape log tracking
- Context manager for connections

CRITICAL: All operations are immutable - input objects are NEVER mutated.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any

from yellowbrick.models import Pitch, ScrapeLog


# Default schema path relative to this file
DEFAULT_SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


class YellowbrickDB:
    """
    Database interface for Yellowbrick pitch data.

    Uses SQLite with upsert semantics based on pitch_id uniqueness.
    Supports context manager protocol for automatic connection management.

    Usage:
        with YellowbrickDB(":memory:") as db:
            is_new = db.upsert_pitch(pitch)
            recent = db.get_recent_pitches(days=30)
    """

    def __init__(
        self,
        db_path: str | Path,
        schema_path: Path | None = None,
    ) -> None:
        """
        Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory.
            schema_path: Optional custom path to schema.sql file.

        Raises:
            FileNotFoundError: If schema file does not exist.
        """
        self._db_path = str(db_path)
        self._schema_path = schema_path or DEFAULT_SCHEMA_PATH

        if not self._schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self._schema_path}")

        self._conn: sqlite3.Connection = self._connect()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """Create database connection with optimized settings."""
        conn = sqlite3.connect(
            self._db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        # Use row factory for easier access
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_schema(self) -> None:
        """Execute schema.sql to create tables, views, and indexes."""
        schema_sql = self._schema_path.read_text()
        self._conn.executescript(schema_sql)
        self._conn.commit()

    def __enter__(self) -> "YellowbrickDB":
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager, commit or rollback based on exception."""
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()

    def upsert_pitch(self, pitch: Pitch) -> bool:
        """
        Insert new pitch or update existing pitch.

        Uses pitch_id as the unique identifier. If pitch_id exists,
        updates all fields except first_seen_at (preserves original).

        CRITICAL: Does NOT mutate the input Pitch object.

        Args:
            pitch: Pitch object to insert or update.

        Returns:
            True if new pitch was inserted, False if existing was updated.
        """
        # Extract values from pitch WITHOUT mutating it
        # Create new dict to avoid any mutation
        values = {
            "ticker": pitch.ticker,
            "feed_type": pitch.feed_type,
            "pitch_id": pitch.pitch_id,
            "author": pitch.author,
            "author_type": pitch.author_type,
            "pitch_date": _format_datetime(pitch.pitch_date),
            "pitch_type": pitch.pitch_type,
            "title": pitch.title,
            "summary": pitch.summary,
            "full_content": pitch.full_content,
            "reasoning": pitch.reasoning,
            "target_price": (
                float(pitch.target_price) if pitch.target_price is not None else None
            ),
            "time_horizon": pitch.time_horizon,
            "source_url": pitch.source_url,
            "filing_type": pitch.filing_type,
            "position_size": pitch.position_size,
            "metadata": json.dumps(pitch.metadata) if pitch.metadata is not None else None,
            "first_seen_at": _format_datetime(pitch.first_seen_at),
            "last_updated_at": _format_datetime(pitch.last_updated_at),
            "is_active": 1 if pitch.is_active else 0,
        }

        # Check if pitch already exists
        cursor = self._conn.execute(
            "SELECT id, first_seen_at FROM yellowbrick_pitches WHERE pitch_id = ?",
            (pitch.pitch_id,),
        )
        existing = cursor.fetchone()

        if existing is None:
            # Insert new pitch
            columns = list(values.keys())
            placeholders = ", ".join("?" for _ in columns)
            column_names = ", ".join(columns)

            self._conn.execute(
                f"INSERT INTO yellowbrick_pitches ({column_names}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            self._conn.commit()
            return True
        else:
            # Update existing pitch - preserve first_seen_at
            # Remove first_seen_at from update (preserve original)
            update_values = {k: v for k, v in values.items() if k != "first_seen_at"}

            set_clause = ", ".join(f"{k} = ?" for k in update_values.keys())

            self._conn.execute(
                f"UPDATE yellowbrick_pitches SET {set_clause} WHERE pitch_id = ?",
                tuple(list(update_values.values()) + [pitch.pitch_id]),
            )
            self._conn.commit()
            return False

    def save_scrape_log(self, log: ScrapeLog) -> None:
        """
        Save scrape log entry.

        CRITICAL: Does NOT mutate the input ScrapeLog object.

        Args:
            log: ScrapeLog object to save.
        """
        # Extract values WITHOUT mutating
        values = {
            "scrape_timestamp": _format_datetime(log.scrape_timestamp),
            "feed_type": log.feed_type,
            "pitches_found": log.pitches_found,
            "pitches_new": log.pitches_new,
            "pitches_updated": log.pitches_updated,
            "duration_seconds": (
                float(log.duration_seconds) if log.duration_seconds is not None else None
            ),
            "status": log.status,
            "error_message": log.error_message,
        }

        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_names = ", ".join(columns)

        self._conn.execute(
            f"INSERT INTO yellowbrick_scrape_log ({column_names}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        self._conn.commit()

    def get_recent_pitches(
        self,
        days: int,
        feed_type: str | None = None,
        ticker: str | None = None,
    ) -> list[dict]:
        """
        Get pitches from the last N days with optional filters.

        Args:
            days: Number of days to look back.
            feed_type: Optional filter by feed type (big_money, elite).
            ticker: Optional filter by ticker symbol.

        Returns:
            List of pitch dicts ordered by pitch_date descending.
        """
        # Build query with dynamic filters
        query = """
            SELECT
                id, ticker, feed_type, pitch_id, author, author_type,
                pitch_date, pitch_type, title, summary, full_content,
                reasoning, target_price, time_horizon, source_url,
                filing_type, position_size, metadata, first_seen_at,
                last_updated_at, is_active
            FROM yellowbrick_pitches
            WHERE DATE(pitch_date) >= DATE('now', ?)
              AND is_active = 1
        """
        params: list[Any] = [f"-{days} days"]

        if feed_type is not None:
            query += " AND feed_type = ?"
            params.append(feed_type)

        if ticker is not None:
            query += " AND ticker = ?"
            params.append(ticker)

        query += " ORDER BY pitch_date DESC"

        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()

        # Convert to list of dicts (new objects, not references)
        return [_row_to_dict(row) for row in rows]

    def get_scrape_health(self) -> list[dict]:
        """
        Get aggregated scrape health statistics per feed type.

        Returns:
            List of health stats dicts from v_scrape_health view.
        """
        cursor = self._conn.execute("SELECT * FROM v_scrape_health")
        rows = cursor.fetchall()

        return [_row_to_dict(row) for row in rows]


def _format_datetime(dt: datetime | None) -> str | None:
    """Format datetime to ISO string for SQLite storage."""
    if dt is None:
        return None
    return dt.isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert sqlite3.Row to dict (creates new dict, no mutation)."""
    return dict(row)
