"""Tests for summarizer module."""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from fmp_data_client.config import FMPConfig, Tier
from fmp_data_client.models.transcripts import EarningsTranscript
from fmp_data_client.models.filings import SECFiling
from fmp_data_client.summarizer.base import BaseSummarizer
from fmp_data_client.summarizer.transcripts import TranscriptSummarizer
from fmp_data_client.summarizer.filings import FilingSummarizer


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_config():
    """Create mock FMP config with summarization enabled."""
    return FMPConfig(
        api_key="test_fmp_key",
        tier=Tier.STARTER,
        summarization_enabled=True,
        anthropic_api_key="test_anthropic_key",
        default_model="claude-3-haiku-20240307",
    )


@pytest.fixture
def mock_config_no_summarization():
    """Create mock FMP config with summarization disabled."""
    return FMPConfig(
        api_key="test_fmp_key",
        tier=Tier.STARTER,
        summarization_enabled=False,
    )


@pytest.fixture
def sample_transcript():
    """Create sample earnings transcript."""
    return EarningsTranscript(
        symbol="AAPL",
        quarter=1,
        year=2024,
        date="2024-01-25",
        content="""
        Apple Q1 2024 Earnings Call

        CEO: We are pleased to announce record revenue of $119.6 billion, up 2% YoY.
        iPhone revenue was $69.7 billion, up 6%. Services revenue reached an all-time high of $23.1 billion.

        CFO: Gross margin was 45.9%, reflecting strong product mix. Operating expenses were $14.3 billion.
        We returned $27 billion to shareholders through dividends and buybacks.

        Q&A:
        Analyst: What's your outlook for China?
        CEO: We see China as a very important market. We're investing in local partnerships
        and seeing strong demand for our latest products.
        """,
    )


@pytest.fixture
def sample_filing():
    """Create sample SEC filing."""
    return SECFiling(
        symbol="AAPL",
        cik="0000320193",
        filing_date="2024-01-26",
        accepted_date="2024-01-26T16:30:00.000Z",
        filing_type="10-Q",
        accession_number="0000320193-24-000006",
        link="https://example.com/filing",
        final_link="https://example.com/filing/final",
    )


@pytest.fixture
def mock_anthropic_response():
    """Create mock Anthropic API response."""
    mock_response = Mock()
    mock_response.content = [Mock(text=json.dumps({
        "executive_summary": "Apple reported strong Q1 results with record revenue.",
        "key_metrics": ["Revenue: $119.6B (+2% YoY)", "iPhone: $69.7B (+6%)"],
        "forward_guidance": "Management expressed confidence in China market.",
        "strategic_themes": ["Product innovation", "Services growth"],
        "sentiment": "bullish",
    }))]
    mock_response.usage = Mock(input_tokens=1000, output_tokens=200)
    return mock_response


# ============================================================================
# BaseSummarizer Tests
# ============================================================================


class TestBaseSummarizerInit:
    """Tests for BaseSummarizer initialization."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    def test_init_success(self, mock_anthropic_class, mock_config):
        """Test successful initialization."""
        summarizer = BaseSummarizer(mock_config)

        assert summarizer.config == mock_config
        assert summarizer.model == mock_config.default_model
        assert summarizer.total_input_tokens == 0
        assert summarizer.total_output_tokens == 0
        mock_anthropic_class.assert_called_once_with(api_key=mock_config.anthropic_api_key)

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    def test_init_custom_model(self, mock_anthropic_class, mock_config):
        """Test initialization with custom model."""
        custom_model = "claude-3-sonnet-20240229"
        summarizer = BaseSummarizer(mock_config, model=custom_model)

        assert summarizer.model == custom_model

    def test_init_summarization_disabled(self, mock_config_no_summarization):
        """Test that initialization fails when summarization disabled."""
        with pytest.raises(ValueError, match="Summarization is not enabled"):
            BaseSummarizer(mock_config_no_summarization)

    def test_init_no_api_key(self):
        """Test that initialization fails without API key."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="anthropic_api_key"):
            config = FMPConfig(
                api_key="test_fmp_key",
                tier=Tier.STARTER,
                summarization_enabled=True,
                anthropic_api_key=None,
            )


class TestBaseSummarizerCallClaude:
    """Tests for _call_claude() method."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_call_claude_success(self, mock_anthropic_class, mock_config):
        """Test successful Claude API call."""
        # Setup mock
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text="Test summary response")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = BaseSummarizer(mock_config)
        result = await summarizer._call_claude("Test prompt")

        assert result == "Test summary response"
        assert summarizer.total_input_tokens == 100
        assert summarizer.total_output_tokens == 50
        mock_client.messages.create.assert_called_once()

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_call_claude_with_system_prompt(self, mock_anthropic_class, mock_config):
        """Test Claude API call with system prompt."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text="Response")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = BaseSummarizer(mock_config)
        result = await summarizer._call_claude(
            "Test prompt",
            system_prompt="You are a financial analyst.",
        )

        assert result == "Response"
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a financial analyst."

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_call_claude_api_error(self, mock_anthropic_class, mock_config):
        """Test handling of API errors."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        summarizer = BaseSummarizer(mock_config)

        with pytest.raises(Exception, match="API error"):
            await summarizer._call_claude("Test prompt")


class TestBaseSummarizerTokenTracking:
    """Tests for token usage tracking."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_token_usage_tracking(self, mock_anthropic_class, mock_config):
        """Test that token usage is tracked correctly."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # First call
        mock_response1 = Mock()
        mock_response1.content = [Mock(text="Response 1")]
        mock_response1.usage = Mock(input_tokens=100, output_tokens=50)

        # Second call
        mock_response2 = Mock()
        mock_response2.content = [Mock(text="Response 2")]
        mock_response2.usage = Mock(input_tokens=200, output_tokens=75)

        mock_client.messages.create = AsyncMock(side_effect=[mock_response1, mock_response2])

        summarizer = BaseSummarizer(mock_config)

        await summarizer._call_claude("Prompt 1")
        await summarizer._call_claude("Prompt 2")

        usage = summarizer.get_token_usage()
        assert usage["input_tokens"] == 300
        assert usage["output_tokens"] == 125
        assert usage["total_tokens"] == 425

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    def test_reset_token_usage(self, mock_anthropic_class, mock_config):
        """Test resetting token usage counters."""
        summarizer = BaseSummarizer(mock_config)
        summarizer.total_input_tokens = 1000
        summarizer.total_output_tokens = 500

        summarizer.reset_token_usage()

        assert summarizer.total_input_tokens == 0
        assert summarizer.total_output_tokens == 0


class TestBaseSummarizerContextManager:
    """Tests for async context manager."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_context_manager(self, mock_anthropic_class, mock_config):
        """Test using summarizer as async context manager."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        async with BaseSummarizer(mock_config) as summarizer:
            assert summarizer is not None

        mock_client.close.assert_called_once()


# ============================================================================
# TranscriptSummarizer Tests
# ============================================================================


class TestTranscriptSummarizerInit:
    """Tests for TranscriptSummarizer initialization."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    def test_init_default_model(self, mock_anthropic_class, mock_config):
        """Test that Haiku is used by default for cost efficiency."""
        summarizer = TranscriptSummarizer(mock_config)

        assert summarizer.model == "claude-3-haiku-20240307"

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    def test_init_custom_model(self, mock_anthropic_class, mock_config):
        """Test initialization with custom model."""
        summarizer = TranscriptSummarizer(mock_config, model="claude-3-sonnet-20240229")

        assert summarizer.model == "claude-3-sonnet-20240229"


class TestTranscriptSummarizerSummarize:
    """Tests for transcript summarization."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarize_transcript_success(
        self, mock_anthropic_class, mock_config, sample_transcript
    ):
        """Test successful transcript summarization."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Mock Claude response as formatted text (not JSON)
        mock_text_response = """**Executive Summary**
Apple reported strong Q1 results.

**Key Metrics**
- Revenue: $119.6B

**Forward Guidance**
Positive outlook for China.

**Strategic Themes**
- Innovation
- Services growth

**Sentiment**
bullish

**Q&A Highlights**
- Strong China performance discussed
"""
        mock_response = Mock()
        mock_response.content = [Mock(text=mock_text_response)]
        mock_response.usage = Mock(input_tokens=1000, output_tokens=200)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = TranscriptSummarizer(mock_config)
        result = await summarizer.summarize_transcript(sample_transcript)

        assert result["executive_summary"] == "Apple reported strong Q1 results."
        assert "bullish" in result["sentiment"]
        assert "key_metrics" in result
        assert len(result["key_metrics"]) > 0
        mock_client.messages.create.assert_called_once()

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarize_transcript_no_sentiment(
        self, mock_anthropic_class, mock_config, sample_transcript
    ):
        """Test summarization without sentiment analysis."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Mock Claude response as formatted text (not JSON)
        mock_text_response = """**Executive Summary**
Apple reported Q1 results.

**Key Metrics**
- Revenue: $119.6B
"""
        mock_response = Mock()
        mock_response.content = [Mock(text=mock_text_response)]
        mock_response.usage = Mock(input_tokens=1000, output_tokens=200)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = TranscriptSummarizer(mock_config)
        result = await summarizer.summarize_transcript(
            sample_transcript, include_sentiment=False
        )

        assert "executive_summary" in result
        assert result["executive_summary"] == "Apple reported Q1 results."

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarize_transcript_api_error(
        self, mock_anthropic_class, mock_config, sample_transcript
    ):
        """Test handling of API errors during summarization."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        summarizer = TranscriptSummarizer(mock_config)

        with pytest.raises(Exception):
            await summarizer.summarize_transcript(sample_transcript)


# ============================================================================
# FilingSummarizer Tests
# ============================================================================


class TestFilingSummarizerInit:
    """Tests for FilingSummarizer initialization."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    def test_init_default_model(self, mock_anthropic_class, mock_config):
        """Test that Haiku is used by default."""
        summarizer = FilingSummarizer(mock_config)

        assert summarizer.model == "claude-3-haiku-20240307"


class TestFilingSummarizerSummarize:
    """Tests for filing summarization."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarize_filing_success(
        self, mock_anthropic_class, mock_config, sample_filing
    ):
        """Test successful filing summarization."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Mock Claude response as formatted text (not JSON)
        mock_text_response = """**Executive Summary**
Apple filed 10-Q for Q1 2024.

**Material Changes**
- Revenue increased 2%

**Risk Factors**
- Competition in smartphone market

**Key Takeaways**
- Strong quarter overall
"""
        mock_response = Mock()
        mock_response.content = [Mock(text=mock_text_response)]
        mock_response.usage = Mock(input_tokens=2000, output_tokens=300)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = FilingSummarizer(mock_config)

        # Need filing content for summarization (at least 100 chars)
        filing_content = "This is test filing content with material information about the company's quarterly financial results and business operations. Revenue increased by 2% compared to the previous quarter."
        result = await summarizer.summarize_filing(sample_filing, filing_content)

        assert result["executive_summary"] == "Apple filed 10-Q for Q1 2024."
        assert "material_changes" in result
        assert len(result["material_changes"]) > 0
        assert "risk_factors" in result

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarize_filing_quick_mode(
        self, mock_anthropic_class, mock_config, sample_filing
    ):
        """Test quick summarization mode."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Mock simple text response for quick_summary method
        mock_text = "Quick summary of 10-Q. Strong results overall."
        mock_response = Mock()
        mock_response.content = [Mock(text=mock_text)]
        mock_response.usage = Mock(input_tokens=500, output_tokens=100)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = FilingSummarizer(mock_config)
        filing_content = "This is test filing content with material information about the company's quarterly financial results and business operations."

        # Use quick_summary method instead of summarize_filing
        result = await summarizer.quick_summary(filing_content, filing_type="10-Q")

        assert result == mock_text.strip()
        # Quick mode should use fewer tokens
        assert summarizer.total_input_tokens < 1000

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarize_filing_different_types(
        self, mock_anthropic_class, mock_config
    ):
        """Test summarization of different filing types."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Mock Claude response as formatted text (not JSON)
        mock_text_response = """**Executive Summary**
8-K filing summary about material event.

**Key Takeaways**
- Material event reported
"""
        mock_response = Mock()
        mock_response.content = [Mock(text=mock_text_response)]
        mock_response.usage = Mock(input_tokens=1000, output_tokens=200)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = FilingSummarizer(mock_config)

        # Test 8-K filing
        filing_8k = SECFiling(
            symbol="AAPL",
            cik="0000320193",
            filing_date="2024-01-26",
            accepted_date="2024-01-26T16:30:00.000Z",
            filing_type="8-K",
            accession_number="0000320193-24-000007",
            link="https://example.com/8k",
            final_link="https://example.com/8k/final",
        )

        # Filing content must be at least 100 characters
        filing_content = "This is an 8-K filing content describing a material corporate event. The company announced significant business developments that require immediate disclosure to investors and the SEC."
        result = await summarizer.summarize_filing(filing_8k, filing_content)

        assert "executive_summary" in result
        assert result["executive_summary"] == "8-K filing summary about material event."
        # Verify the prompt mentions 8-K
        call_args = mock_client.messages.create.call_args
        assert "8-K" in str(call_args)


# ============================================================================
# Integration Tests
# ============================================================================


class TestSummarizerIntegration:
    """Integration tests for summarizer components."""

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_multiple_summarizations_token_tracking(
        self, mock_anthropic_class, mock_config, sample_transcript
    ):
        """Test token tracking across multiple summarizations."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Multiple responses
        responses = []
        for i in range(3):
            mock_resp = Mock()
            mock_resp.content = [Mock(text=json.dumps({"summary": f"Summary {i}"}))]
            mock_resp.usage = Mock(input_tokens=1000, output_tokens=200)
            responses.append(mock_resp)

        mock_client.messages.create = AsyncMock(side_effect=responses)

        summarizer = TranscriptSummarizer(mock_config)

        # Summarize three times
        for _ in range(3):
            await summarizer.summarize_transcript(sample_transcript)

        usage = summarizer.get_token_usage()
        assert usage["input_tokens"] == 3000
        assert usage["output_tokens"] == 600
        assert usage["total_tokens"] == 3600

    @patch("fmp_data_client.summarizer.base.AsyncAnthropic")
    async def test_summarizer_reusability(
        self, mock_anthropic_class, mock_config, sample_transcript
    ):
        """Test that summarizer can be reused for multiple calls."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({"summary": "Test"}))]
        mock_response.usage = Mock(input_tokens=1000, output_tokens=200)
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        summarizer = TranscriptSummarizer(mock_config)

        # First call
        result1 = await summarizer.summarize_transcript(sample_transcript)
        assert result1 is not None

        # Second call should work
        result2 = await summarizer.summarize_transcript(sample_transcript)
        assert result2 is not None

        # Should have been called twice
        assert mock_client.messages.create.call_count == 2
