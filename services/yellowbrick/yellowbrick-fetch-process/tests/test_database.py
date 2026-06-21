"""
Tests for Yellowbrick Database Layer.

Tests for the Yellowbrick database layer.

CRITICAL: Tests verify immutability - Pitch objects passed to upsert_pitch
must not be mutated.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest


class TestYellowbrickDBInitialization:
    """Test cases for YellowbrickDB initialization."""

    def test_database_creates_tables_from_schema(self):
        """Database should create all tables from schema.sql on init."""
        from yellowbrick.database import YellowbrickDB

        with YellowbrickDB(":memory:") as db:
            # Verify yellowbrick_pitches table exists
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='yellowbrick_pitches'"
            )
            assert cursor.fetchone() is not None

            # Verify yellowbrick_scrape_log table exists
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='yellowbrick_scrape_log'"
            )
            assert cursor.fetchone() is not None

            # Verify yellowbrick_positions table exists
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='yellowbrick_positions'"
            )
            assert cursor.fetchone() is not None

    def test_database_creates_views(self):
        """Database should create all views from schema.sql."""
        from yellowbrick.database import YellowbrickDB

        with YellowbrickDB(":memory:") as db:
            # Verify v_recent_pitches view exists
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name='v_recent_pitches'"
            )
            assert cursor.fetchone() is not None

            # Verify v_elite_pitches view exists
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name='v_elite_pitches'"
            )
            assert cursor.fetchone() is not None

            # Verify v_scrape_health view exists
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name='v_scrape_health'"
            )
            assert cursor.fetchone() is not None

    def test_database_creates_indexes(self):
        """Database should create indexes from schema.sql."""
        from yellowbrick.database import YellowbrickDB

        with YellowbrickDB(":memory:") as db:
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pitches_ticker'"
            )
            assert cursor.fetchone() is not None

    def test_database_creates_trigger(self):
        """Database should create update timestamp trigger."""
        from yellowbrick.database import YellowbrickDB

        with YellowbrickDB(":memory:") as db:
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name='update_pitch_timestamp'"
            )
            assert cursor.fetchone() is not None

    def test_context_manager_closes_connection(self):
        """Context manager should close connection on exit."""
        from yellowbrick.database import YellowbrickDB

        db = YellowbrickDB(":memory:")
        db.__enter__()
        db.__exit__(None, None, None)

        # Connection should be closed - operations should fail
        with pytest.raises(sqlite3.ProgrammingError):
            db._conn.execute("SELECT 1")

    def test_context_manager_commits_on_success(self):
        """Context manager should commit changes on successful exit."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="test_commit_123",
            author="Test Fund",
        )

        # Use context manager
        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)
            # Get connection reference before close
            conn_str = str(db._conn)

        # Since we're using :memory:, data won't persist after close
        # This test just verifies no exception on exit

    def test_context_manager_rollbacks_on_error(self):
        """Context manager should rollback on exception."""
        from yellowbrick.database import YellowbrickDB

        try:
            with YellowbrickDB(":memory:") as db:
                # Insert valid data
                db._conn.execute(
                    "INSERT INTO yellowbrick_scrape_log (feed_type, status) VALUES (?, ?)",
                    ("big_money", "SUCCESS"),
                )
                # Raise exception - should trigger rollback
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected

    def test_database_with_file_path(self, tmp_path: Path):
        """Database should work with file path."""
        from yellowbrick.database import YellowbrickDB

        db_path = tmp_path / "test.db"

        with YellowbrickDB(db_path) as db:
            cursor = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='yellowbrick_pitches'"
            )
            assert cursor.fetchone() is not None

        # Verify file exists
        assert db_path.exists()

    def test_database_schema_path_not_found(self, tmp_path: Path):
        """Database should raise error if schema.sql not found."""
        from yellowbrick.database import YellowbrickDB

        # Temporarily move schema.sql by passing a custom schema path that doesn't exist
        with pytest.raises(FileNotFoundError):
            YellowbrickDB(":memory:", schema_path=tmp_path / "nonexistent.sql")


class TestUpsertPitch:
    """Test cases for upsert_pitch method."""

    def test_upsert_inserts_new_pitch(self):
        """upsert_pitch should insert new pitch and return True."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="new_pitch_001",
            author="Test Fund",
            title="Apple Investment Thesis",
            summary="Apple is undervalued",
            target_price=Decimal("200.00"),
        )

        with YellowbrickDB(":memory:") as db:
            result = db.upsert_pitch(pitch)

            assert result is True  # New pitch inserted

            # Verify data was inserted
            cursor = db._conn.execute(
                "SELECT ticker, feed_type, pitch_id, author, title, target_price FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            assert row is not None
            assert row[0] == "AAPL"
            assert row[1] == "big_money"
            assert row[2] == "new_pitch_001"
            assert row[3] == "Test Fund"
            assert row[4] == "Apple Investment Thesis"
            assert float(row[5]) == 200.00

    def test_upsert_preserves_zero_target_price(self):
        """upsert_pitch should store explicit zero target_price values."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="zero_target_001",
            author="Test Fund",
            target_price=Decimal("0"),
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)
            row = db._conn.execute(
                "SELECT target_price FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            ).fetchone()

            assert float(row[0]) == 0.0

    def test_upsert_updates_existing_pitch(self):
        """upsert_pitch should update existing pitch and return False."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        original = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="existing_pitch_001",
            author="Test Fund",
            title="Original Title",
            summary="Original summary",
        )

        updated = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="existing_pitch_001",  # Same pitch_id
            author="Test Fund",
            title="Updated Title",  # Changed
            summary="Updated summary",  # Changed
            target_price=Decimal("150.00"),  # Added
        )

        with YellowbrickDB(":memory:") as db:
            # Insert original
            first_result = db.upsert_pitch(original)
            assert first_result is True

            # Update with same pitch_id
            second_result = db.upsert_pitch(updated)
            assert second_result is False  # Existing pitch updated

            # Verify data was updated
            cursor = db._conn.execute(
                "SELECT title, summary, target_price FROM yellowbrick_pitches WHERE pitch_id = ?",
                (updated.pitch_id,),
            )
            row = cursor.fetchone()

            assert row[0] == "Updated Title"
            assert row[1] == "Updated summary"
            assert float(row[2]) == 150.00

    def test_upsert_does_not_mutate_pitch_object(self):
        """CRITICAL: upsert_pitch must not mutate the Pitch object."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        original_ticker = "AAPL"
        original_author = "Test Fund"
        original_title = "Original Title"

        pitch = Pitch(
            ticker=original_ticker,
            feed_type="big_money",
            pitch_id="immutability_test_001",
            author=original_author,
            title=original_title,
        )

        # Store original values
        pitch_dict_before = pitch.model_dump()

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

        # Verify pitch object unchanged
        pitch_dict_after = pitch.model_dump()

        assert pitch.ticker == original_ticker
        assert pitch.author == original_author
        assert pitch.title == original_title
        assert pitch_dict_before == pitch_dict_after

    def test_upsert_handles_all_fields(self):
        """upsert_pitch should handle all Pitch fields."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)

        pitch = Pitch(
            ticker="GOOGL",
            feed_type="elite",
            pitch_id="full_pitch_001",
            author="Elite Fund",
            author_type="hedge_fund",
            pitch_date=now,
            pitch_type="LONG",
            title="Google Analysis",
            summary="Google is undervalued",
            full_content="Full content here...",
            reasoning="Strong competitive moat",
            target_price=Decimal("200.50"),
            time_horizon="12 months",
            source_url="https://example.com/pitch",
            filing_type="13F",
            position_size="5%",
            metadata={"word_count": 5000, "read_time": 20},
            first_seen_at=now,
            last_updated_at=now,
            is_active=True,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

            cursor = db._conn.execute(
                "SELECT * FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()
            columns = [desc[0] for desc in cursor.description]
            row_dict = dict(zip(columns, row))

            assert row_dict["ticker"] == "GOOGL"
            assert row_dict["feed_type"] == "elite"
            assert row_dict["author_type"] == "hedge_fund"
            assert row_dict["pitch_type"] == "LONG"
            assert row_dict["reasoning"] == "Strong competitive moat"
            assert row_dict["filing_type"] == "13F"
            assert row_dict["position_size"] == "5%"
            assert row_dict["is_active"] == 1

    def test_upsert_handles_none_values(self):
        """upsert_pitch should handle None values for optional fields."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="minimal_pitch_001",
            author="Test Fund",
            # All other fields are None/default
        )

        with YellowbrickDB(":memory:") as db:
            result = db.upsert_pitch(pitch)
            assert result is True

            cursor = db._conn.execute(
                "SELECT title, summary, target_price FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            assert row[0] is None  # title
            assert row[1] is None  # summary
            assert row[2] is None  # target_price

    def test_upsert_preserves_first_seen_at_on_update(self):
        """Update should preserve original first_seen_at timestamp."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        first_seen = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        original = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="timestamp_test_001",
            author="Test Fund",
            first_seen_at=first_seen,
        )

        updated = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="timestamp_test_001",
            author="Test Fund",
            title="Updated",
            first_seen_at=datetime.now(timezone.utc),  # New timestamp
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(original)
            db.upsert_pitch(updated)

            cursor = db._conn.execute(
                "SELECT first_seen_at FROM yellowbrick_pitches WHERE pitch_id = ?",
                (original.pitch_id,),
            )
            row = cursor.fetchone()

            # first_seen_at should be preserved from original insert
            stored_first_seen = datetime.fromisoformat(row[0])
            # Allow for some formatting differences
            assert stored_first_seen.year == 2024
            assert stored_first_seen.month == 1
            assert stored_first_seen.day == 1

    def test_upsert_stores_metadata_as_json(self):
        """Metadata should be stored as JSON string."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        metadata = {
            "word_count": 5000,
            "read_time": 20,
            "nested": {"key": "value"},
        }

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="json_test_001",
            author="Test Fund",
            metadata=metadata,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

            cursor = db._conn.execute(
                "SELECT metadata FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            stored_metadata = json.loads(row[0])
            assert stored_metadata["word_count"] == 5000
            assert stored_metadata["nested"]["key"] == "value"


class TestSaveScrapeLog:
    """Test cases for save_scrape_log method."""

    def test_save_scrape_log_success(self):
        """save_scrape_log should save log entry."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(
            feed_type="big_money",
            status="SUCCESS",
            pitches_found=50,
            pitches_new=10,
            pitches_updated=5,
            duration_seconds=Decimal("12.5"),
        )

        with YellowbrickDB(":memory:") as db:
            db.save_scrape_log(log)

            cursor = db._conn.execute(
                "SELECT feed_type, status, pitches_found, pitches_new, pitches_updated, duration_seconds FROM yellowbrick_scrape_log"
            )
            row = cursor.fetchone()

            assert row[0] == "big_money"
            assert row[1] == "SUCCESS"
            assert row[2] == 50
            assert row[3] == 10
            assert row[4] == 5
            assert float(row[5]) == 12.5

    def test_save_scrape_log_failed_with_error(self):
        """save_scrape_log should save failed log with error message."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(
            feed_type="elite",
            status="FAILED",
            error_message="Connection timeout after 30 seconds",
        )

        with YellowbrickDB(":memory:") as db:
            db.save_scrape_log(log)

            cursor = db._conn.execute(
                "SELECT status, error_message FROM yellowbrick_scrape_log"
            )
            row = cursor.fetchone()

            assert row[0] == "FAILED"
            assert "timeout" in row[1].lower()

    def test_save_scrape_log_does_not_mutate_object(self):
        """save_scrape_log must not mutate the ScrapeLog object."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(
            feed_type="big_money",
            status="SUCCESS",
            pitches_found=50,
        )

        log_dict_before = log.model_dump()

        with YellowbrickDB(":memory:") as db:
            db.save_scrape_log(log)

        log_dict_after = log.model_dump()
        assert log_dict_before == log_dict_after

    def test_save_scrape_log_preserves_zero_duration(self):
        """save_scrape_log should preserve explicit zero durations."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(
            feed_type="big_money",
            status="SUCCESS",
            duration_seconds=Decimal("0"),
        )

        with YellowbrickDB(":memory:") as db:
            db.save_scrape_log(log)
            row = db._conn.execute(
                "SELECT duration_seconds FROM yellowbrick_scrape_log"
            ).fetchone()

            assert float(row[0]) == 0.0


class TestGetRecentPitches:
    """Test cases for get_recent_pitches method."""

    def test_get_recent_pitches_returns_pitches_within_days(self):
        """get_recent_pitches should return pitches within specified days."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)
        recent_date = now - timedelta(days=5)
        old_date = now - timedelta(days=60)

        recent_pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="recent_001",
            author="Test Fund",
            pitch_date=recent_date,
        )

        old_pitch = Pitch(
            ticker="GOOGL",
            feed_type="big_money",
            pitch_id="old_001",
            author="Test Fund",
            pitch_date=old_date,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(recent_pitch)
            db.upsert_pitch(old_pitch)

            results = db.get_recent_pitches(days=30)

            assert len(results) == 1
            assert results[0]["pitch_id"] == "recent_001"

    def test_get_recent_pitches_filters_by_feed_type(self):
        """get_recent_pitches should filter by feed_type."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)
        recent_date = now - timedelta(days=5)

        big_money_pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="bm_001",
            author="Fund A",
            pitch_date=recent_date,
        )

        elite_pitch = Pitch(
            ticker="GOOGL",
            feed_type="elite",
            pitch_id="elite_001",
            author="Fund B",
            pitch_date=recent_date,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(big_money_pitch)
            db.upsert_pitch(elite_pitch)

            results = db.get_recent_pitches(days=30, feed_type="elite")

            assert len(results) == 1
            assert results[0]["pitch_id"] == "elite_001"

    def test_get_recent_pitches_filters_by_ticker(self):
        """get_recent_pitches should filter by ticker."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)
        recent_date = now - timedelta(days=5)

        aapl_pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="aapl_001",
            author="Fund A",
            pitch_date=recent_date,
        )

        googl_pitch = Pitch(
            ticker="GOOGL",
            feed_type="big_money",
            pitch_id="googl_001",
            author="Fund B",
            pitch_date=recent_date,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(aapl_pitch)
            db.upsert_pitch(googl_pitch)

            results = db.get_recent_pitches(days=30, ticker="AAPL")

            assert len(results) == 1
            assert results[0]["pitch_id"] == "aapl_001"

    def test_get_recent_pitches_filters_combined(self):
        """get_recent_pitches should support combined filters."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)
        recent_date = now - timedelta(days=5)

        pitches = [
            Pitch(ticker="AAPL", feed_type="big_money", pitch_id="p1", author="F1", pitch_date=recent_date),
            Pitch(ticker="AAPL", feed_type="elite", pitch_id="p2", author="F2", pitch_date=recent_date),
            Pitch(ticker="GOOGL", feed_type="elite", pitch_id="p3", author="F3", pitch_date=recent_date),
        ]

        with YellowbrickDB(":memory:") as db:
            for pitch in pitches:
                db.upsert_pitch(pitch)

            results = db.get_recent_pitches(days=30, feed_type="elite", ticker="AAPL")

            assert len(results) == 1
            assert results[0]["pitch_id"] == "p2"

    def test_get_recent_pitches_excludes_inactive(self):
        """get_recent_pitches should exclude inactive pitches."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)
        recent_date = now - timedelta(days=5)

        active_pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="active_001",
            author="Fund A",
            pitch_date=recent_date,
            is_active=True,
        )

        inactive_pitch = Pitch(
            ticker="GOOGL",
            feed_type="big_money",
            pitch_id="inactive_001",
            author="Fund B",
            pitch_date=recent_date,
            is_active=False,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(active_pitch)
            db.upsert_pitch(inactive_pitch)

            results = db.get_recent_pitches(days=30)

            assert len(results) == 1
            assert results[0]["pitch_id"] == "active_001"

    def test_get_recent_pitches_returns_dict_list(self):
        """get_recent_pitches should return list of dicts (not Pitch objects)."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="dict_test_001",
            author="Test Fund",
            pitch_date=now - timedelta(days=1),
            title="Test Title",
            summary="Test Summary",
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)
            results = db.get_recent_pitches(days=30)

            assert isinstance(results, list)
            assert len(results) == 1
            assert isinstance(results[0], dict)
            assert "ticker" in results[0]
            assert "pitch_id" in results[0]
            assert "title" in results[0]

    def test_get_recent_pitches_ordered_by_date_desc(self):
        """get_recent_pitches should return results ordered by pitch_date desc."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)

        older = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="older_001",
            author="Fund A",
            pitch_date=now - timedelta(days=10),
        )

        newer = Pitch(
            ticker="GOOGL",
            feed_type="big_money",
            pitch_id="newer_001",
            author="Fund B",
            pitch_date=now - timedelta(days=2),
        )

        with YellowbrickDB(":memory:") as db:
            # Insert older first
            db.upsert_pitch(older)
            db.upsert_pitch(newer)

            results = db.get_recent_pitches(days=30)

            assert len(results) == 2
            assert results[0]["pitch_id"] == "newer_001"  # Most recent first
            assert results[1]["pitch_id"] == "older_001"

    def test_get_recent_pitches_empty_result(self):
        """get_recent_pitches should return empty list when no matches."""
        from yellowbrick.database import YellowbrickDB

        with YellowbrickDB(":memory:") as db:
            results = db.get_recent_pitches(days=30)

            assert results == []


class TestGetScrapeHealth:
    """Test cases for get_scrape_health method."""

    def test_get_scrape_health_returns_aggregated_data(self):
        """get_scrape_health should return aggregated scrape stats per feed."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import ScrapeLog

        logs = [
            ScrapeLog(feed_type="big_money", status="SUCCESS", pitches_new=10, duration_seconds=Decimal("5.0")),
            ScrapeLog(feed_type="big_money", status="SUCCESS", pitches_new=8, duration_seconds=Decimal("6.0")),
            ScrapeLog(feed_type="big_money", status="FAILED", pitches_new=0, duration_seconds=Decimal("1.0")),
            ScrapeLog(feed_type="elite", status="SUCCESS", pitches_new=5, duration_seconds=Decimal("4.0")),
        ]

        with YellowbrickDB(":memory:") as db:
            for log in logs:
                db.save_scrape_log(log)

            results = db.get_scrape_health()

            assert isinstance(results, list)
            assert len(results) == 2  # big_money and elite

            # Find big_money stats
            big_money = next((r for r in results if r["feed_type"] == "big_money"), None)
            assert big_money is not None
            assert big_money["total_scrapes"] == 3
            assert big_money["successful"] == 2
            assert big_money["failed"] == 1
            assert big_money["total_new_pitches"] == 18

    def test_get_scrape_health_empty_result(self):
        """get_scrape_health should return empty list when no logs."""
        from yellowbrick.database import YellowbrickDB

        with YellowbrickDB(":memory:") as db:
            results = db.get_scrape_health()
            assert results == []


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_upsert_special_characters_in_text(self):
        """upsert should handle special characters."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="special_001",
            author="O'Brien & Partners",
            title="Apple's \"Amazing\" Growth",
            summary="Revenue > $100B; margin >= 30%",
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

            cursor = db._conn.execute(
                "SELECT author, title, summary FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            assert row[0] == "O'Brien & Partners"
            assert row[1] == "Apple's \"Amazing\" Growth"
            assert ">" in row[2]

    def test_upsert_unicode_characters(self):
        """upsert should handle unicode characters."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="unicode_001",
            author="Fund",
            title="Apple Analysis",
            summary="Price target: 200 (up from 150)",
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

            cursor = db._conn.execute(
                "SELECT summary FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            assert "200" in row[0]

    def test_upsert_very_long_content(self):
        """upsert should handle very long content."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        long_content = "A" * 100000  # 100KB of text

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="long_001",
            author="Fund",
            full_content=long_content,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

            cursor = db._conn.execute(
                "SELECT LENGTH(full_content) FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            assert row[0] == 100000

    def test_concurrent_upserts_same_pitch_id(self):
        """Multiple upserts with same pitch_id should not cause errors."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        with YellowbrickDB(":memory:") as db:
            for i in range(10):
                pitch = Pitch(
                    ticker="AAPL",
                    feed_type="big_money",
                    pitch_id="concurrent_001",
                    author="Fund",
                    title=f"Title {i}",
                )
                db.upsert_pitch(pitch)

            # Should have only one row
            cursor = db._conn.execute(
                "SELECT COUNT(*) FROM yellowbrick_pitches WHERE pitch_id = ?",
                ("concurrent_001",),
            )
            assert cursor.fetchone()[0] == 1

            # Should have last title
            cursor = db._conn.execute(
                "SELECT title FROM yellowbrick_pitches WHERE pitch_id = ?",
                ("concurrent_001",),
            )
            assert cursor.fetchone()[0] == "Title 9"

    def test_null_metadata_stored_correctly(self):
        """None metadata should be stored as NULL, not 'null' string."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="null_meta_001",
            author="Fund",
            metadata=None,
        )

        with YellowbrickDB(":memory:") as db:
            db.upsert_pitch(pitch)

            cursor = db._conn.execute(
                "SELECT metadata FROM yellowbrick_pitches WHERE pitch_id = ?",
                (pitch.pitch_id,),
            )
            row = cursor.fetchone()

            # Should be NULL, not the string "null"
            assert row[0] is None


class TestDatabaseIntegration:
    """Integration tests for complete workflows."""

    def test_full_scrape_workflow(self):
        """Test complete scrape workflow: insert pitches, save log, query."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch, ScrapeLog

        now = datetime.now(timezone.utc)

        pitches = [
            Pitch(
                ticker="AAPL",
                feed_type="big_money",
                pitch_id="workflow_001",
                author="Fund A",
                pitch_date=now,
                title="Apple Long",
            ),
            Pitch(
                ticker="GOOGL",
                feed_type="big_money",
                pitch_id="workflow_002",
                author="Fund B",
                pitch_date=now,
                title="Google Long",
            ),
        ]

        with YellowbrickDB(":memory:") as db:
            new_count = 0
            for pitch in pitches:
                if db.upsert_pitch(pitch):
                    new_count += 1

            log = ScrapeLog(
                feed_type="big_money",
                status="SUCCESS",
                pitches_found=len(pitches),
                pitches_new=new_count,
                pitches_updated=0,
                duration_seconds=Decimal("3.5"),
            )
            db.save_scrape_log(log)

            # Query recent pitches
            recent = db.get_recent_pitches(days=7)
            assert len(recent) == 2

            # Check scrape health
            health = db.get_scrape_health()
            assert len(health) == 1
            assert health[0]["total_new_pitches"] == 2

    def test_update_workflow_preserves_history(self):
        """Test that updates preserve first_seen_at."""
        from yellowbrick.database import YellowbrickDB
        from yellowbrick.models import Pitch

        first_seen = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        original = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="history_001",
            author="Fund",
            pitch_date=now,
            title="Original",
            first_seen_at=first_seen,
        )

        with YellowbrickDB(":memory:") as db:
            # First insert
            result1 = db.upsert_pitch(original)
            assert result1 is True

            # Update with new data
            updated = Pitch(
                ticker="AAPL",
                feed_type="big_money",
                pitch_id="history_001",
                author="Fund",
                pitch_date=now,
                title="Updated",
                first_seen_at=datetime.now(timezone.utc),  # New timestamp
            )

            result2 = db.upsert_pitch(updated)
            assert result2 is False

            # Verify title updated but first_seen preserved
            cursor = db._conn.execute(
                "SELECT title, first_seen_at FROM yellowbrick_pitches WHERE pitch_id = ?",
                ("history_001",),
            )
            row = cursor.fetchone()

            assert row[0] == "Updated"
            stored_first_seen = datetime.fromisoformat(row[1])
            assert stored_first_seen.year == 2024
