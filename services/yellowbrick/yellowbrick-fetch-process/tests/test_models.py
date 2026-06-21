"""
Tests for Yellowbrick Pydantic models.

Tests for the Yellowbrick Pydantic data models.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError


class TestPitchModel:
    """Test cases for Pitch model."""

    def test_pitch_creation_with_required_fields(self):
        """Pitch should be created with required fields."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        assert pitch.ticker == "AAPL"
        assert pitch.feed_type == "big_money"
        assert pitch.pitch_id == "12345"
        assert pitch.author == "Test Fund"

    def test_pitch_creation_with_all_fields(self):
        """Pitch should support all schema fields."""
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)

        pitch = Pitch(
            ticker="GOOGL",
            feed_type="elite",
            pitch_id="pitch_126819",
            author="Sohra Peak",
            author_type="professional",
            pitch_date=now,
            pitch_type="long",
            title="Investment Memorandum: GOOGL",
            summary="Undervalued tech giant",
            full_content="Full pitch content here...",
            reasoning="Strong competitive moat",
            target_price=Decimal("200.50"),
            time_horizon="12 months",
            source_url="https://example.com/pitch",
            filing_type="FUND LETTER",
            position_size="3.5%",
            metadata={"word_count": 16321, "read_time": 55},
            first_seen_at=now,
            last_updated_at=now,
            is_active=True,
        )

        assert pitch.ticker == "GOOGL"
        assert pitch.author_type == "professional"
        assert pitch.target_price == Decimal("200.50")
        assert pitch.metadata["word_count"] == 16321

    def test_ticker_validator_uppercase(self):
        """Ticker should be converted to uppercase."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="aapl",  # lowercase
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        assert pitch.ticker == "AAPL"  # Should be uppercase

    def test_ticker_validator_with_suffix(self):
        """Ticker with exchange suffix should be normalized."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="dbo.to",  # lowercase with suffix
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        assert pitch.ticker == "DBO.TO"

    def test_ticker_rejects_empty(self):
        """Ticker should reject empty strings."""
        from yellowbrick.models import Pitch

        with pytest.raises(ValidationError) as exc_info:
            Pitch(
                ticker="",
                feed_type="big_money",
                pitch_id="12345",
                author="Test Fund",
            )

        assert "ticker" in str(exc_info.value).lower()

    def test_ticker_rejects_too_long(self):
        """Ticker should reject strings over 10 characters."""
        from yellowbrick.models import Pitch

        with pytest.raises(ValidationError) as exc_info:
            Pitch(
                ticker="TOOLONGTICKER",  # 13 chars
                feed_type="big_money",
                pitch_id="12345",
                author="Test Fund",
            )

        assert "ticker" in str(exc_info.value).lower()

    def test_feed_type_validator_valid_values(self):
        """Feed type should accept valid values."""
        from yellowbrick.models import Pitch

        for feed_type in ["big_money", "elite"]:
            pitch = Pitch(
                ticker="AAPL",
                feed_type=feed_type,
                pitch_id="12345",
                author="Test Fund",
            )
            assert pitch.feed_type == feed_type

    def test_feed_type_validator_rejects_invalid(self):
        """Feed type should reject invalid values."""
        from yellowbrick.models import Pitch

        with pytest.raises(ValidationError) as exc_info:
            Pitch(
                ticker="AAPL",
                feed_type="invalid_feed",
                pitch_id="12345",
                author="Test Fund",
            )

        assert "feed_type" in str(exc_info.value).lower()

    def test_pitch_date_validator_accepts_datetime(self):
        """Pitch date should accept datetime objects."""
        from yellowbrick.models import Pitch

        now = datetime.now(timezone.utc)

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
            pitch_date=now,
        )

        assert pitch.pitch_date == now

    def test_pitch_date_validator_accepts_iso_string(self):
        """Pitch date should accept ISO format strings."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
            pitch_date="2025-12-05",
        )

        assert pitch.pitch_date.year == 2025
        assert pitch.pitch_date.month == 12
        assert pitch.pitch_date.day == 5

    def test_pitch_date_validator_accepts_none(self):
        """Pitch date should accept None."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
            pitch_date=None,
        )

        assert pitch.pitch_date is None

    def test_pitch_immutability(self):
        """Pitch should be immutable (frozen)."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        with pytest.raises((AttributeError, ValidationError)):
            pitch.ticker = "GOOGL"  # Should fail - model is frozen

    def test_pitch_model_copy(self):
        """Pitch should support immutable copy with changes."""
        from yellowbrick.models import Pitch

        original = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        # Create new instance with updated field
        updated = original.model_copy(update={"ticker": "GOOGL"})

        assert original.ticker == "AAPL"  # Original unchanged
        assert updated.ticker == "GOOGL"  # New instance has update

    def test_target_price_accepts_decimal(self):
        """Target price should accept Decimal."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
            target_price=Decimal("150.75"),
        )

        assert pitch.target_price == Decimal("150.75")

    def test_target_price_accepts_float(self):
        """Target price should accept float and convert to Decimal."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
            target_price=150.75,
        )

        assert pitch.target_price == Decimal("150.75")

    def test_metadata_accepts_dict(self):
        """Metadata should accept arbitrary JSON-compatible dict."""
        from yellowbrick.models import Pitch

        metadata = {
            "word_count": 16321,
            "read_time": 55,
            "company_data": {
                "market_cap": 220471257,
                "pe_ratio": 25.75,
            },
            "returns": {
                "one_month": 0.06,
                "three_month": 0.12,
            },
        }

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
            metadata=metadata,
        )

        assert pitch.metadata["word_count"] == 16321
        assert pitch.metadata["company_data"]["market_cap"] == 220471257

    def test_is_active_defaults_to_true(self):
        """is_active should default to True."""
        from yellowbrick.models import Pitch

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        assert pitch.is_active is True

    def test_timestamps_default_to_now(self):
        """Timestamps should default to current time."""
        from yellowbrick.models import Pitch

        before = datetime.now(timezone.utc)

        pitch = Pitch(
            ticker="AAPL",
            feed_type="big_money",
            pitch_id="12345",
            author="Test Fund",
        )

        after = datetime.now(timezone.utc)

        assert before <= pitch.first_seen_at <= after
        assert before <= pitch.last_updated_at <= after


class TestScrapeLogModel:
    """Test cases for ScrapeLog model."""

    def test_scrape_log_creation_minimal(self):
        """ScrapeLog should be created with minimal fields."""
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(
            feed_type="big_money",
            status="SUCCESS",
        )

        assert log.feed_type == "big_money"
        assert log.status == "SUCCESS"

    def test_scrape_log_creation_full(self):
        """ScrapeLog should support all fields."""
        from yellowbrick.models import ScrapeLog

        now = datetime.now(timezone.utc)

        log = ScrapeLog(
            scrape_timestamp=now,
            feed_type="elite",
            pitches_found=50,
            pitches_new=10,
            pitches_updated=5,
            duration_seconds=Decimal("12.5"),
            status="SUCCESS",
            error_message=None,
        )

        assert log.pitches_found == 50
        assert log.pitches_new == 10
        assert log.duration_seconds == Decimal("12.5")

    def test_scrape_log_status_validator_valid(self):
        """Status should accept valid values."""
        from yellowbrick.models import ScrapeLog

        valid_statuses = ["SUCCESS", "PARTIAL", "FAILED", "PENDING"]

        for status in valid_statuses:
            log = ScrapeLog(feed_type="big_money", status=status)
            assert log.status == status

    def test_scrape_log_status_validator_invalid(self):
        """Status should reject invalid values."""
        from yellowbrick.models import ScrapeLog

        with pytest.raises(ValidationError) as exc_info:
            ScrapeLog(feed_type="big_money", status="INVALID")

        assert "status" in str(exc_info.value).lower()

    def test_scrape_log_feed_type_validator(self):
        """Feed type should only accept valid values."""
        from yellowbrick.models import ScrapeLog

        with pytest.raises(ValidationError) as exc_info:
            ScrapeLog(feed_type="invalid", status="SUCCESS")

        assert "feed_type" in str(exc_info.value).lower()

    def test_scrape_log_failed_with_error_message(self):
        """Failed scrape should include error message."""
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(
            feed_type="big_money",
            status="FAILED",
            error_message="Connection timeout after 30 seconds",
        )

        assert log.status == "FAILED"
        assert "timeout" in log.error_message.lower()

    def test_scrape_log_immutability(self):
        """ScrapeLog should be immutable."""
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(feed_type="big_money", status="SUCCESS")

        with pytest.raises((AttributeError, ValidationError)):
            log.status = "FAILED"

    def test_scrape_log_timestamp_defaults_to_now(self):
        """Timestamp should default to current time."""
        from yellowbrick.models import ScrapeLog

        before = datetime.now(timezone.utc)

        log = ScrapeLog(feed_type="big_money", status="SUCCESS")

        after = datetime.now(timezone.utc)

        assert before <= log.scrape_timestamp <= after

    def test_scrape_log_counts_default_to_zero(self):
        """Pitch counts should default to 0."""
        from yellowbrick.models import ScrapeLog

        log = ScrapeLog(feed_type="big_money", status="SUCCESS")

        assert log.pitches_found == 0
        assert log.pitches_new == 0
        assert log.pitches_updated == 0


class TestFeedType:
    """Test FeedType enum."""

    def test_feed_type_enum_values(self):
        """FeedType enum should have expected values."""
        from yellowbrick.models import FeedType

        assert FeedType.BIG_MONEY.value == "big_money"
        assert FeedType.ELITE.value == "elite"

    def test_feed_type_enum_iteration(self):
        """FeedType should be iterable."""
        from yellowbrick.models import FeedType

        values = [ft.value for ft in FeedType]
        assert "big_money" in values
        assert "elite" in values


class TestScrapeStatus:
    """Test ScrapeStatus enum."""

    def test_scrape_status_enum_values(self):
        """ScrapeStatus enum should have expected values."""
        from yellowbrick.models import ScrapeStatus

        assert ScrapeStatus.SUCCESS.value == "SUCCESS"
        assert ScrapeStatus.PARTIAL.value == "PARTIAL"
        assert ScrapeStatus.FAILED.value == "FAILED"
        assert ScrapeStatus.PENDING.value == "PENDING"
