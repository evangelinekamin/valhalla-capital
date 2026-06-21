"""
Tests for Yellowbrick JSON parser.

Tests for the Yellowbrick JSON parser module.
"""

from datetime import datetime
from decimal import Decimal

import pytest


class TestParseRawPitch:
    """Test cases for parse_raw_pitch function."""

    def test_parse_complete_pitch(self, sample_pitch_json):
        """Should parse complete pitch JSON with all fields."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        # Core identification
        assert pitch.ticker == "DBO.TO"
        assert pitch.feed_type == "big_money"
        assert pitch.pitch_id == "126819"
        assert pitch.author == "Sohra Peak"

    def test_parse_pitch_author_details(self, sample_pitch_json):
        """Should extract author details correctly."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.author == "Sohra Peak"
        assert pitch.author_type == "professional"

    def test_parse_pitch_dates(self, sample_pitch_json):
        """Should parse dates correctly."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.pitch_date is not None
        assert pitch.pitch_date.year == 2025
        assert pitch.pitch_date.month == 12
        assert pitch.pitch_date.day == 5

    def test_parse_pitch_content(self, sample_pitch_json):
        """Should extract content fields."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.title == "Investment Memorandum: D-BOX Technologies Inc. (DBO)"
        assert pitch.summary == "Undervalued haptic technology company with strong growth potential"
        assert "D-BOX Technologies" in pitch.full_content
        assert pitch.pitch_type == "bullish"

    def test_parse_pitch_target_price(self, sample_pitch_json):
        """Should parse target price."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.target_price == Decimal("2.62")

    def test_parse_pitch_source_url(self, sample_pitch_json):
        """Should extract source URL."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.source_url == "https://www.joinyellowbrick.com/pitch/dbo-to-investment-memo"

    def test_parse_pitch_filing_type(self, sample_pitch_json):
        """Should extract filing type from source field."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.filing_type == "FUND LETTER"

    def test_parse_pitch_metadata(self, sample_pitch_json):
        """Should store additional data in metadata."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.metadata is not None
        # Company data
        assert pitch.metadata.get("company_name") == "D-BOX Technologies Inc."
        assert pitch.metadata.get("market_cap") == 220471257
        assert pitch.metadata.get("pe_ratio") == pytest.approx(25.747724)
        assert pitch.metadata.get("ev_ebitda") == pytest.approx(16.802343)
        # Returns data
        assert pitch.metadata.get("one_month_return") == pytest.approx(0.06)
        assert pitch.metadata.get("three_month_return") == pytest.approx(0.12)
        assert pitch.metadata.get("one_year_return") == pytest.approx(0.45)
        # Content metadata
        assert pitch.metadata.get("word_count") == 16321
        assert pitch.metadata.get("read_time") == 55
        assert pitch.metadata.get("category") == "growth"

    def test_parse_minimal_pitch(self, sample_pitch_minimal_json):
        """Should handle minimal pitch with missing optional fields."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_minimal_json, feed_type="big_money")

        assert pitch.ticker == "AAPL"
        assert pitch.pitch_id == "99999"
        assert pitch.author == "Unknown"  # Default when missing
        assert pitch.pitch_type == "neutral"

    def test_parse_bearish_pitch(self, sample_pitch_bearish_json):
        """Should parse bearish pitch correctly."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_bearish_json, feed_type="elite")

        assert pitch.ticker == "XYZ"
        assert pitch.feed_type == "elite"
        assert pitch.pitch_type == "bearish"
        assert pitch.target_price == Decimal("15.00")

    def test_parse_pitch_normalizes_ticker(self):
        """Should normalize ticker to uppercase."""
        from yellowbrick.parser import parse_raw_pitch

        raw_data = {
            "id": 12345,
            "givenTicker": "aapl",  # lowercase
            "sentiment": "bullish",
        }

        pitch = parse_raw_pitch(raw_data, feed_type="big_money")

        assert pitch.ticker == "AAPL"

    def test_parse_pitch_handles_null_values(self):
        """Should handle null values gracefully."""
        from yellowbrick.parser import parse_raw_pitch

        raw_data = {
            "id": 12345,
            "givenTicker": "AAPL",
            "sentiment": "neutral",
            "priceTarget": None,
            "author": None,
            "company": None,
            "returns": None,
        }

        pitch = parse_raw_pitch(raw_data, feed_type="big_money")

        assert pitch.ticker == "AAPL"
        assert pitch.target_price is None
        assert pitch.author == "Unknown"

    def test_parse_pitch_extracts_nested_company_data(self, sample_pitch_json):
        """Should extract nested company data."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.metadata["company_name"] == "D-BOX Technologies Inc."
        assert pitch.metadata["sector"] == "Household Durables"
        assert pitch.metadata["exchange"] == "TSX"
        assert pitch.metadata["currency"] == "CAD"
        assert pitch.metadata["current_price"] == pytest.approx(0.99)

    def test_parse_pitch_extracts_author_returns(self, sample_pitch_json):
        """Should extract author returns to metadata."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.metadata.get("author_twitter") == "@JonCukierwar"
        assert pitch.metadata.get("author_url") == "https://sohrapeakcapital.com"
        assert pitch.metadata.get("is_top_author") is True

    def test_parse_pitch_handles_missing_nested_objects(self):
        """Should handle missing nested objects (author, company, returns)."""
        from yellowbrick.parser import parse_raw_pitch

        raw_data = {
            "id": 12345,
            "givenTicker": "AAPL",
            "sentiment": "bullish",
            # No author, company, or returns objects
        }

        pitch = parse_raw_pitch(raw_data, feed_type="big_money")

        assert pitch.ticker == "AAPL"
        assert pitch.author == "Unknown"
        # Metadata can be None or empty dict when no nested objects
        assert pitch.metadata is None or pitch.metadata.get("company_name") is None

    def test_parse_pitch_preserves_original_price(self, sample_pitch_json):
        """Should preserve original price in metadata."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        assert pitch.metadata.get("original_price") == pytest.approx(0.83)

    def test_parse_pitch_returns_immutable_object(self, sample_pitch_json):
        """Should return immutable Pitch object."""
        from yellowbrick.parser import parse_raw_pitch

        pitch = parse_raw_pitch(sample_pitch_json, feed_type="big_money")

        with pytest.raises((AttributeError, Exception)):
            pitch.ticker = "GOOGL"


class TestParsePitchesList:
    """Test cases for parse_pitches_list function."""

    def test_parse_empty_list(self):
        """Should handle empty list."""
        from yellowbrick.parser import parse_pitches_list

        result = parse_pitches_list([], feed_type="big_money")

        assert result == []

    def test_parse_multiple_pitches(self, sample_pitches_list_json):
        """Should parse list of pitches."""
        from yellowbrick.parser import parse_pitches_list

        result = parse_pitches_list(sample_pitches_list_json, feed_type="big_money")

        assert len(result) == 2
        assert result[0].ticker == "DBO.TO"
        assert result[1].ticker == "GOOGL"

    def test_parse_list_skips_invalid_entries(self):
        """Should skip invalid entries and continue parsing."""
        from yellowbrick.parser import parse_pitches_list

        raw_data = [
            {"id": 1, "givenTicker": "AAPL", "sentiment": "bullish"},
            {"invalid": "data"},  # Missing required fields
            {"id": 2, "givenTicker": "GOOGL", "sentiment": "neutral"},
        ]

        result = parse_pitches_list(raw_data, feed_type="big_money")

        assert len(result) == 2
        assert result[0].ticker == "AAPL"
        assert result[1].ticker == "GOOGL"

    def test_parse_list_returns_new_list(self, sample_pitches_list_json):
        """Should return new list (immutability)."""
        from yellowbrick.parser import parse_pitches_list

        original = sample_pitches_list_json.copy()

        result = parse_pitches_list(sample_pitches_list_json, feed_type="big_money")

        # Original unchanged
        assert sample_pitches_list_json == original
        # Result is new list
        assert result is not sample_pitches_list_json


class TestExtractCompanyData:
    """Test cases for extract_company_data helper."""

    def test_extract_company_data_complete(self, sample_pitch_json):
        """Should extract complete company data."""
        from yellowbrick.parser import extract_company_data

        result = extract_company_data(sample_pitch_json.get("company", {}))

        assert result["company_name"] == "D-BOX Technologies Inc."
        assert result["ticker_symbol"] == "DBO"
        assert result["sector"] == "Household Durables"
        assert result["exchange"] == "TSX"
        assert result["currency"] == "CAD"
        assert result["market_cap"] == 220471257
        assert result["current_price"] == pytest.approx(0.99)
        assert result["pe_ratio"] == pytest.approx(25.747724)
        assert result["ev_ebitda"] == pytest.approx(16.802343)

    def test_extract_company_data_empty(self):
        """Should handle empty company object."""
        from yellowbrick.parser import extract_company_data

        result = extract_company_data({})

        assert result == {}

    def test_extract_company_data_partial(self):
        """Should handle partial company data."""
        from yellowbrick.parser import extract_company_data

        company_data = {
            "companyName": "Test Corp",
            "tickerSymbol": "TEST",
            # Missing other fields
        }

        result = extract_company_data(company_data)

        assert result["company_name"] == "Test Corp"
        assert result["ticker_symbol"] == "TEST"
        assert result.get("market_cap") is None


class TestExtractReturnsData:
    """Test cases for extract_returns_data helper."""

    def test_extract_returns_complete(self, sample_pitch_json):
        """Should extract complete returns data."""
        from yellowbrick.parser import extract_returns_data

        result = extract_returns_data(sample_pitch_json.get("returns", {}))

        assert result["original_price"] == pytest.approx(0.83)
        assert result["current_price"] == pytest.approx(0.99)
        assert result["one_month_return"] == pytest.approx(0.06)
        assert result["three_month_return"] == pytest.approx(0.12)
        assert result["six_month_return"] == pytest.approx(0.25)
        assert result["one_year_return"] == pytest.approx(0.45)

    def test_extract_returns_empty(self):
        """Should handle empty returns object."""
        from yellowbrick.parser import extract_returns_data

        result = extract_returns_data({})

        assert result == {}

    def test_extract_returns_with_nulls(self):
        """Should handle null return values."""
        from yellowbrick.parser import extract_returns_data

        returns_data = {
            "originalPrice": 25.00,
            "currentPrice": None,
            "oneMonthReturn": 0.05,
            "threeMonthReturn": None,
            "oneYearReturn": None,
        }

        result = extract_returns_data(returns_data)

        assert result["original_price"] == pytest.approx(25.00)
        assert result.get("current_price") is None
        assert result["one_month_return"] == pytest.approx(0.05)
        assert result.get("three_month_return") is None


class TestExtractAuthorData:
    """Test cases for extract_author_data helper."""

    def test_extract_author_complete(self, sample_pitch_json):
        """Should extract complete author data."""
        from yellowbrick.parser import extract_author_data

        result = extract_author_data(sample_pitch_json.get("author", {}))

        assert result["author_name"] == "Sohra Peak"
        assert result["author_id"] == "sohra_peak"
        assert result["twitter"] == "@JonCukierwar"
        assert result["base_url"] == "https://sohrapeakcapital.com"
        assert result["is_professional"] is True
        assert result["is_top_author"] is True

    def test_extract_author_empty(self):
        """Should handle empty author object."""
        from yellowbrick.parser import extract_author_data

        result = extract_author_data({})

        assert result == {}

    def test_extract_author_anonymous(self, sample_pitch_bearish_json):
        """Should handle anonymous author."""
        from yellowbrick.parser import extract_author_data

        result = extract_author_data(sample_pitch_bearish_json.get("author", {}))

        assert result["author_name"] == "Anonymous Short Seller"
        assert result["is_professional"] is False
        assert result.get("twitter") is None


class TestDeterminePitchType:
    """Test cases for determine_pitch_type helper."""

    def test_determine_pitch_type_bullish(self):
        """Should return 'bullish' for bullish sentiment."""
        from yellowbrick.parser import determine_pitch_type

        assert determine_pitch_type("bullish") == "bullish"

    def test_determine_pitch_type_bearish(self):
        """Should return 'bearish' for bearish sentiment."""
        from yellowbrick.parser import determine_pitch_type

        assert determine_pitch_type("bearish") == "bearish"

    def test_determine_pitch_type_neutral(self):
        """Should return 'neutral' for neutral sentiment."""
        from yellowbrick.parser import determine_pitch_type

        assert determine_pitch_type("neutral") == "neutral"

    def test_determine_pitch_type_none(self):
        """Should return 'neutral' for None."""
        from yellowbrick.parser import determine_pitch_type

        assert determine_pitch_type(None) == "neutral"

    def test_determine_pitch_type_unknown(self):
        """Should return 'neutral' for unknown values."""
        from yellowbrick.parser import determine_pitch_type

        assert determine_pitch_type("something_else") == "neutral"


class TestDetermineAuthorType:
    """Test cases for determine_author_type helper."""

    def test_author_type_professional(self):
        """Should return 'professional' for professional authors."""
        from yellowbrick.parser import determine_author_type

        author_data = {"isProfessional": True}

        assert determine_author_type(author_data) == "professional"

    def test_author_type_retail(self):
        """Should return 'retail' for non-professional authors."""
        from yellowbrick.parser import determine_author_type

        author_data = {"isProfessional": False}

        assert determine_author_type(author_data) == "retail"

    def test_author_type_missing(self):
        """Should return None for missing isProfessional."""
        from yellowbrick.parser import determine_author_type

        author_data = {}

        assert determine_author_type(author_data) is None
