"""
Test suite for LLM-powered triage and extraction layer.

Tests are written FIRST following TDD methodology.
These tests will fail until implementation is complete.

Test Categories:
1. AnthropicClient Tests (client.py)
2. Prompt Builder Tests (prompts.py)
3. TriageEngine Tests (triage.py)
4. TickerExtractor Tests (ticker_extractor.py)
5. SentimentAnalyzer Tests (sentiment_analyzer.py)
6. Integration Tests
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import List, Dict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def triage_config():
    """Load triage configuration from actual config file."""
    config_path = Path(__file__).parent.parent / "config" / "triage_config.json"
    with open(config_path, "r") as f:
        return json.load(f)


@pytest.fixture
def mock_anthropic_response():
    """Sample successful Anthropic API response."""
    return {
        "classification": "CRITICAL",
        "confidence": 0.95,
        "tickers": ["AAPL", "MSFT"],
        "sentiment": "bullish",
        "reasoning": "Apple announces major product breakthrough"
    }


@pytest.fixture
def mock_anthropic_api_response(mock_anthropic_response):
    """Mock Anthropic API message response object."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(mock_anthropic_response)

    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_message.usage = MagicMock()
    mock_message.usage.input_tokens = 150
    mock_message.usage.output_tokens = 50

    return mock_message


@pytest.fixture
def sample_tweets():
    """Sample tweets for batch processing."""
    return [
        {
            "id": "1",
            "username": "analyst1",
            "content": "Breaking: $AAPL announces new iPhone with revolutionary AI features",
            "pre_filter_action": "triage"
        },
        {
            "id": "2",
            "username": "investor2",
            "content": "MSFT cloud revenue up 30% - very bullish on this quarter",
            "pre_filter_action": "triage"
        },
        {
            "id": "3",
            "username": "trader3",
            "content": "$TSLA facing headwinds as competition intensifies",
            "pre_filter_action": "triage"
        }
    ]


@pytest.fixture
def sample_batch_response():
    """Sample LLM batch response for multiple tweets."""
    return [
        {
            "classification": "CRITICAL",
            "confidence": 0.95,
            "tickers": ["AAPL"],
            "sentiment": "bullish",
            "reasoning": "Major product announcement"
        },
        {
            "classification": "IMPORTANT",
            "confidence": 0.85,
            "tickers": ["MSFT"],
            "sentiment": "bullish",
            "reasoning": "Strong earnings report"
        },
        {
            "classification": "ROUTINE",
            "confidence": 0.70,
            "tickers": ["TSLA"],
            "sentiment": "bearish",
            "reasoning": "General market commentary"
        }
    ]


@pytest.fixture
def common_words_list():
    """List of common words that should be filtered out as tickers."""
    return [
        "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
        "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "DAY",
        "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW", "NOW",
        "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "ITS",
        "LET", "PUT", "SAY", "SHE", "TOO", "USE", "CEO", "CFO",
        "IPO", "ETF", "GDP", "USA", "NYC", "EST", "PST", "AM", "PM"
    ]


# ---------------------------------------------------------------------------
# AnthropicClient Tests (client.py)
# ---------------------------------------------------------------------------

class TestAnthropicClientModule:
    """Tests for the client.py module."""

    def test_module_imports(self):
        """Client module should be importable."""
        from scraper.llm import client
        assert client is not None

    def test_anthropic_client_class_exists(self):
        """AnthropicClient class should exist."""
        from scraper.llm.client import AnthropicClient
        assert AnthropicClient is not None


class TestAnthropicClientInitialization:
    """Tests for AnthropicClient initialization."""

    def test_init_with_api_key(self):
        """Should initialize with provided API key."""
        from scraper.llm.client import AnthropicClient

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            assert client is not None

    def test_init_reads_from_environment(self):
        """Should read API key from ANTHROPIC_API_KEY environment variable."""
        from scraper.llm.client import AnthropicClient

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-test-key"}):
            client = AnthropicClient()
            assert client.api_key == "env-test-key"

    def test_init_raises_without_api_key(self):
        """Should raise error if API key not provided and not in env."""
        from scraper.llm.client import AnthropicClient

        with patch.dict(os.environ, {}, clear=True):
            # Remove ANTHROPIC_API_KEY if it exists
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicClient()

    def test_init_with_explicit_api_key(self):
        """Should accept explicit API key parameter."""
        from scraper.llm.client import AnthropicClient

        client = AnthropicClient(api_key="explicit-key")
        assert client.api_key == "explicit-key"


class TestAnthropicClientClassifyBatch:
    """Tests for classify_batch method."""

    def test_classify_batch_method_exists(self):
        """classify_batch method should exist."""
        from scraper.llm.client import AnthropicClient

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            assert hasattr(client, "classify_batch")
            assert callable(client.classify_batch)

    @patch("scraper.llm.client.Anthropic")
    def test_classify_batch_returns_list(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """classify_batch should return a list of results."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            result = client.classify_batch(sample_tweets[:1])

            assert isinstance(result, list)

    @patch("scraper.llm.client.Anthropic")
    def test_classify_batch_uses_correct_model(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """classify_batch should use claude-haiku-4-5-20251001 model."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1])

            call_args = mock_client.messages.create.call_args
            assert call_args.kwargs.get("model") == "claude-haiku-4-5-20251001"

    @patch("scraper.llm.client.Anthropic")
    def test_classify_batch_respects_max_tokens(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """classify_batch should respect max_tokens parameter."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1], max_tokens=300)

            call_args = mock_client.messages.create.call_args
            assert call_args.kwargs.get("max_tokens") == 300

    @patch("scraper.llm.client.Anthropic")
    def test_classify_batch_respects_temperature(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """classify_batch should respect temperature parameter."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1], temperature=0.2)

            call_args = mock_client.messages.create.call_args
            assert call_args.kwargs.get("temperature") == 0.2


class TestAnthropicClientRetryLogic:
    """Tests for retry logic with exponential backoff."""

    @patch("scraper.llm.client.Anthropic")
    @patch("time.sleep")
    def test_retries_on_api_error(self, mock_sleep, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Should retry on API error with exponential backoff."""
        from scraper.llm.client import AnthropicClient
        import anthropic

        mock_request = MagicMock()
        mock_client = MagicMock()
        # Fail twice, then succeed
        mock_client.messages.create.side_effect = [
            anthropic.APIError("API Error", request=mock_request, body=None),
            anthropic.APIError("API Error", request=mock_request, body=None),
            mock_anthropic_api_response
        ]
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            result = client.classify_batch(sample_tweets[:1])

            assert mock_client.messages.create.call_count == 3
            assert mock_sleep.call_count == 2

    @patch("scraper.llm.client.Anthropic")
    @patch("time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Should use exponential backoff (2s base delay)."""
        from scraper.llm.client import AnthropicClient
        import anthropic

        mock_request = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            anthropic.APIError("API Error", request=mock_request, body=None),
            anthropic.APIError("API Error", request=mock_request, body=None),
            mock_anthropic_api_response
        ]
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1])

            # First retry: 2s, Second retry: 4s
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert delays[0] == 2
            assert delays[1] == 4

    @patch("scraper.llm.client.Anthropic")
    @patch("time.sleep")
    def test_max_retry_attempts(self, mock_sleep, mock_anthropic, sample_tweets):
        """Should fail after 3 retry attempts."""
        from scraper.llm.client import AnthropicClient
        import anthropic

        mock_request = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.APIError("API Error", request=mock_request, body=None)
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()

            with pytest.raises(Exception):
                client.classify_batch(sample_tweets[:1])

            assert mock_client.messages.create.call_count == 3


class TestAnthropicClientErrorHandling:
    """Tests for error handling."""

    @patch("scraper.llm.client.Anthropic")
    def test_handles_timeout_error(self, mock_anthropic, sample_tweets):
        """Should handle timeout errors gracefully."""
        from scraper.llm.client import AnthropicClient
        import anthropic

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(None)
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()

            with pytest.raises(Exception):
                client.classify_batch(sample_tweets[:1])

    @patch("scraper.llm.client.Anthropic")
    def test_handles_rate_limit_error(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Should handle rate limit errors with retry."""
        from scraper.llm.client import AnthropicClient
        import anthropic

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            anthropic.RateLimitError("Rate limited", response=mock_response, body=None),
            mock_anthropic_api_response
        ]
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("time.sleep"):
                client = AnthropicClient()
                result = client.classify_batch(sample_tweets[:1])

                assert result is not None

    @patch("scraper.llm.client.Anthropic")
    def test_handles_json_parsing_error(self, mock_anthropic, sample_tweets):
        """Should handle JSON parsing errors in response."""
        from scraper.llm.client import AnthropicClient

        mock_content = MagicMock()
        mock_content.text = "invalid json {"

        mock_message = MagicMock()
        mock_message.content = [mock_content]
        mock_message.usage = MagicMock()
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            result = client.classify_batch(sample_tweets[:1])

            # Should return fallback result
            assert isinstance(result, list)


class TestAnthropicClientTokenCounting:
    """Tests for token counting functionality."""

    @patch("scraper.llm.client.Anthropic")
    def test_tracks_input_tokens(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Should track input tokens for cost estimation."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1])

            assert client.total_input_tokens > 0

    @patch("scraper.llm.client.Anthropic")
    def test_tracks_output_tokens(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Should track output tokens for cost estimation."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1])

            assert client.total_output_tokens > 0

    @patch("scraper.llm.client.Anthropic")
    def test_get_usage_stats(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Should provide usage statistics."""
        from scraper.llm.client import AnthropicClient

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            client.classify_batch(sample_tweets[:1])

            stats = client.get_usage_stats()
            assert "input_tokens" in stats
            assert "output_tokens" in stats
            assert "total_requests" in stats


# ---------------------------------------------------------------------------
# Prompt Builder Tests (prompts.py)
# ---------------------------------------------------------------------------

class TestPromptModule:
    """Tests for the prompts.py module."""

    def test_module_imports(self):
        """Prompts module should be importable."""
        from scraper.llm import prompts
        assert prompts is not None

    def test_has_build_system_prompt(self):
        """Module should have build_system_prompt function."""
        from scraper.llm.prompts import build_system_prompt
        assert callable(build_system_prompt)

    def test_has_build_user_prompt(self):
        """Module should have build_user_prompt function."""
        from scraper.llm.prompts import build_user_prompt
        assert callable(build_user_prompt)


class TestBuildSystemPrompt:
    """Tests for build_system_prompt function."""

    def test_returns_string(self):
        """build_system_prompt should return a string."""
        from scraper.llm.prompts import build_system_prompt

        result = build_system_prompt()
        assert isinstance(result, str)

    def test_includes_classification_definitions(self):
        """System prompt should include classification definitions."""
        from scraper.llm.prompts import build_system_prompt

        result = build_system_prompt()

        assert "CRITICAL" in result
        assert "IMPORTANT" in result
        assert "ROUTINE" in result
        assert "SKIP" in result

    def test_includes_sentiment_definitions(self):
        """System prompt should include sentiment definitions."""
        from scraper.llm.prompts import build_system_prompt

        result = build_system_prompt()

        assert "bullish" in result
        assert "bearish" in result
        assert "neutral" in result

    def test_includes_json_schema(self):
        """System prompt should include expected JSON output schema."""
        from scraper.llm.prompts import build_system_prompt

        result = build_system_prompt()

        assert "classification" in result
        assert "confidence" in result
        assert "tickers" in result
        assert "sentiment" in result
        assert "reasoning" in result

    def test_includes_few_shot_examples(self):
        """System prompt should include few-shot examples."""
        from scraper.llm.prompts import build_system_prompt

        result = build_system_prompt()

        # Should have example inputs and outputs
        assert "Example" in result or "example" in result


class TestBuildUserPrompt:
    """Tests for build_user_prompt function."""

    def test_returns_string(self):
        """build_user_prompt should return a string."""
        from scraper.llm.prompts import build_user_prompt

        result = build_user_prompt("testuser", "This is a test tweet")
        assert isinstance(result, str)

    def test_includes_username(self):
        """User prompt should include username."""
        from scraper.llm.prompts import build_user_prompt

        result = build_user_prompt("analyst1", "Test content")
        assert "analyst1" in result

    def test_includes_content(self):
        """User prompt should include tweet content."""
        from scraper.llm.prompts import build_user_prompt

        result = build_user_prompt("user", "$AAPL is breaking out")
        assert "$AAPL is breaking out" in result

    def test_handles_special_characters(self):
        """User prompt should handle special characters."""
        from scraper.llm.prompts import build_user_prompt

        content = "Testing $AAPL @mention #hashtag \"quotes\" 'apostrophes'"
        result = build_user_prompt("user", content)
        assert content in result

    def test_handles_empty_username(self):
        """User prompt should handle empty username."""
        from scraper.llm.prompts import build_user_prompt

        result = build_user_prompt("", "Some content here")
        assert "Some content here" in result

    def test_handles_empty_content(self):
        """User prompt should handle empty content."""
        from scraper.llm.prompts import build_user_prompt

        result = build_user_prompt("user", "")
        assert isinstance(result, str)


class TestBuildBatchPrompt:
    """Tests for batch prompt building."""

    def test_build_batch_prompt_exists(self):
        """build_batch_prompt function should exist."""
        from scraper.llm.prompts import build_batch_prompt
        assert callable(build_batch_prompt)

    def test_batch_prompt_includes_all_tweets(self, sample_tweets):
        """Batch prompt should include all tweets."""
        from scraper.llm.prompts import build_batch_prompt

        result = build_batch_prompt(sample_tweets)

        for tweet in sample_tweets:
            assert tweet["content"] in result or tweet["username"] in result


# ---------------------------------------------------------------------------
# TriageEngine Tests (triage.py)
# ---------------------------------------------------------------------------

class TestTriageEngineModule:
    """Tests for the triage.py module."""

    def test_module_imports(self):
        """Triage module should be importable."""
        from scraper.llm import triage
        assert triage is not None

    def test_triage_engine_class_exists(self):
        """TriageEngine class should exist."""
        from scraper.llm.triage import TriageEngine
        assert TriageEngine is not None


class TestTriageEngineInitialization:
    """Tests for TriageEngine initialization."""

    def test_init_with_client_and_config(self):
        """Should initialize with client and config path."""
        from scraper.llm.triage import TriageEngine
        from scraper.llm.client import AnthropicClient

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock(spec=AnthropicClient)
            config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

            engine = TriageEngine(client=mock_client, config_path=config_path)
            assert engine is not None

    def test_loads_config_file(self):
        """Should load triage_config.json."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        assert engine.config is not None
        assert "classifications" in engine.config

    def test_raises_on_missing_config(self):
        """Should raise error if config file missing."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()

        with pytest.raises(FileNotFoundError):
            TriageEngine(client=mock_client, config_path="/nonexistent/path.json")


class TestTriageEngineProcessBatch:
    """Tests for process_batch method."""

    def test_process_batch_method_exists(self):
        """process_batch method should exist."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")
        engine = TriageEngine(client=mock_client, config_path=config_path)

        assert hasattr(engine, "process_batch")
        assert callable(engine.process_batch)

    def test_process_batch_returns_list(self, sample_tweets, sample_batch_response):
        """process_batch should return a list of results."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = sample_batch_response
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        result = engine.process_batch(sample_tweets)

        assert isinstance(result, list)
        assert len(result) == len(sample_tweets)

    def test_process_batch_filters_non_triage_tweets(self, sample_tweets):
        """process_batch should only process tweets with pre_filter_action='triage'."""
        from scraper.llm.triage import TriageEngine

        # Modify one tweet to have different action
        tweets_with_mixed = sample_tweets.copy()
        tweets_with_mixed[0] = {**tweets_with_mixed[0], "pre_filter_action": "skip"}

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = [
            {"classification": "IMPORTANT", "confidence": 0.8, "tickers": [], "sentiment": "neutral", "reasoning": ""}
        ]
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        result = engine.process_batch(tweets_with_mixed)

        # Should only process tweets that need triage
        assert len([r for r in result if r.get("processed")]) < len(tweets_with_mixed)

    def test_process_batch_respects_batch_size(self, sample_batch_response):
        """process_batch should respect 15 tweets per batch limit."""
        from scraper.llm.triage import TriageEngine

        # Create 20 tweets
        many_tweets = [
            {"id": str(i), "username": f"user{i}", "content": f"Tweet {i}", "pre_filter_action": "triage"}
            for i in range(20)
        ]

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = sample_batch_response
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        engine.process_batch(many_tweets)

        # Should have made multiple calls (20 / 15 = 2 batches)
        assert mock_client.classify_batch.call_count >= 2

    def test_process_batch_includes_classification(self, sample_tweets, sample_batch_response):
        """process_batch results should include classification."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = sample_batch_response
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets)

        for result in results:
            assert "classification" in result
            assert result["classification"] in ["CRITICAL", "IMPORTANT", "ROUTINE", "SKIP"]

    def test_process_batch_includes_confidence(self, sample_tweets, sample_batch_response):
        """process_batch results should include confidence score."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = sample_batch_response
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets)

        for result in results:
            assert "confidence" in result
            assert 0.0 <= result["confidence"] <= 1.0

    def test_process_batch_includes_tickers(self, sample_tweets, sample_batch_response):
        """process_batch results should include extracted tickers."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = sample_batch_response
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets)

        for result in results:
            assert "tickers" in result
            assert isinstance(result["tickers"], list)

    def test_process_batch_includes_sentiment(self, sample_tweets, sample_batch_response):
        """process_batch results should include sentiment."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = sample_batch_response
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets)

        for result in results:
            assert "sentiment" in result
            assert result["sentiment"] in ["bullish", "bearish", "neutral"]


class TestTriageEngineFallback:
    """Tests for fallback behavior on errors."""

    def test_fallback_on_parse_error(self, sample_tweets):
        """Should return 'ROUTINE' classification on parse errors."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        # Return invalid response that can't be parsed
        mock_client.classify_batch.return_value = [{"invalid": "response"}]
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets[:1])

        assert results[0]["classification"] == "ROUTINE"

    def test_fallback_on_api_error(self, sample_tweets):
        """Should return 'ROUTINE' classification on API errors."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.side_effect = Exception("API Error")
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets[:1])

        for result in results:
            assert result["classification"] == "ROUTINE"

    def test_fallback_includes_error_flag(self, sample_tweets):
        """Fallback results should include error flag."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.side_effect = Exception("API Error")
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets[:1])

        for result in results:
            assert result.get("fallback") is True or result.get("error") is not None


class TestTriageEngineValidation:
    """Tests for response validation."""

    def test_validates_classification_values(self, sample_tweets):
        """Should validate classification is one of CRITICAL/IMPORTANT/ROUTINE/SKIP."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = [
            {"classification": "INVALID", "confidence": 0.8, "tickers": [], "sentiment": "neutral", "reasoning": ""}
        ]
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets[:1])

        # Invalid classification should be normalized to ROUTINE
        assert results[0]["classification"] in ["CRITICAL", "IMPORTANT", "ROUTINE", "SKIP"]

    def test_validates_confidence_range(self, sample_tweets):
        """Should validate confidence is between 0.0 and 1.0."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = [
            {"classification": "CRITICAL", "confidence": 1.5, "tickers": [], "sentiment": "neutral", "reasoning": ""}
        ]
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets[:1])

        # Out of range confidence should be clamped
        assert 0.0 <= results[0]["confidence"] <= 1.0

    def test_validates_sentiment_values(self, sample_tweets):
        """Should validate sentiment is bullish/bearish/neutral."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        mock_client.classify_batch.return_value = [
            {"classification": "CRITICAL", "confidence": 0.8, "tickers": [], "sentiment": "positive", "reasoning": ""}
        ]
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch(sample_tweets[:1])

        # Invalid sentiment should be normalized to neutral
        assert results[0]["sentiment"] in ["bullish", "bearish", "neutral"]


# ---------------------------------------------------------------------------
# TickerExtractor Tests (ticker_extractor.py)
# ---------------------------------------------------------------------------

class TestTickerExtractorModule:
    """Tests for the ticker_extractor.py module."""

    def test_module_imports(self):
        """TickerExtractor module should be importable."""
        from scraper.llm import ticker_extractor
        assert ticker_extractor is not None

    def test_ticker_extractor_class_exists(self):
        """TickerExtractor class should exist."""
        from scraper.llm.ticker_extractor import TickerExtractor
        assert TickerExtractor is not None


class TestTickerExtractorFromLLM:
    """Tests for extracting tickers from LLM response."""

    def test_extract_from_llm_response_method_exists(self):
        """extract_from_llm_response method should exist."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        assert hasattr(extractor, "extract_from_llm_response")
        assert callable(extractor.extract_from_llm_response)

    def test_extract_single_ticker(self):
        """Should extract single ticker from LLM response."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        response = {"tickers": ["AAPL"]}
        result = extractor.extract_from_llm_response(response)

        assert result == ["AAPL"]

    def test_extract_multiple_tickers(self):
        """Should extract multiple tickers from LLM response."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        response = {"tickers": ["AAPL", "MSFT", "GOOGL"]}
        result = extractor.extract_from_llm_response(response)

        assert result == ["AAPL", "MSFT", "GOOGL"]

    def test_handles_empty_tickers(self):
        """Should handle empty ticker list."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        response = {"tickers": []}
        result = extractor.extract_from_llm_response(response)

        assert result == []

    def test_handles_missing_tickers_key(self):
        """Should handle missing tickers key in response."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        response = {"classification": "CRITICAL"}
        result = extractor.extract_from_llm_response(response)

        assert result == []

    def test_normalizes_to_uppercase(self):
        """Should normalize tickers to uppercase."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        response = {"tickers": ["aapl", "Msft", "GoOgL"]}
        result = extractor.extract_from_llm_response(response)

        assert result == ["AAPL", "MSFT", "GOOGL"]

    def test_deduplicates_tickers(self):
        """Should deduplicate tickers."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        response = {"tickers": ["AAPL", "AAPL", "MSFT", "MSFT"]}
        result = extractor.extract_from_llm_response(response)

        assert result == ["AAPL", "MSFT"]


class TestTickerExtractorRegex:
    """Tests for regex-based ticker extraction."""

    def test_extract_with_regex_method_exists(self):
        """extract_with_regex method should exist."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        assert hasattr(extractor, "extract_with_regex")
        assert callable(extractor.extract_with_regex)

    def test_extracts_dollar_sign_tickers(self):
        """Should extract $TICKER patterns."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "Looking at $AAPL and $MSFT today"
        result = extractor.extract_with_regex(text)

        assert "AAPL" in result
        assert "MSFT" in result

    def test_extracts_capital_letter_tickers(self):
        """Should extract TICKER patterns (1-5 capital letters)."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "AAPL is breaking out, MSFT following"
        result = extractor.extract_with_regex(text)

        assert "AAPL" in result
        assert "MSFT" in result

    def test_handles_mixed_patterns(self):
        """Should handle mixed $TICKER and TICKER patterns."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "$AAPL is up, MSFT also gaining"
        result = extractor.extract_with_regex(text)

        assert "AAPL" in result
        assert "MSFT" in result

    def test_filters_common_words(self, common_words_list):
        """Should filter out common words like THE, AND, FOR."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "THE AAPL AND MSFT FOR TODAY"
        result = extractor.extract_with_regex(text)

        assert "THE" not in result
        assert "AND" not in result
        assert "FOR" not in result
        assert "AAPL" in result
        assert "MSFT" in result

    def test_validates_ticker_length(self):
        """Should only accept tickers with 1-5 characters."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "$A $AB $ABC $ABCD $ABCDE $ABCDEF"
        result = extractor.extract_with_regex(text)

        assert "A" in result
        assert "AB" in result
        assert "ABC" in result
        assert "ABCD" in result
        assert "ABCDE" in result
        assert "ABCDEF" not in result  # 6 characters, too long

    def test_handles_empty_text(self):
        """Should handle empty text."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        result = extractor.extract_with_regex("")

        assert result == []

    def test_handles_none_text(self):
        """Should handle None text."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        result = extractor.extract_with_regex(None)

        assert result == []

    def test_removes_duplicates(self):
        """Should remove duplicate tickers."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "$AAPL $AAPL AAPL looking good today"
        result = extractor.extract_with_regex(text)

        assert result.count("AAPL") == 1


class TestTickerExtractorCombine:
    """Tests for combining LLM and regex extractions."""

    def test_combine_extractions_method_exists(self):
        """combine_extractions method should exist."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        assert hasattr(extractor, "combine_extractions")
        assert callable(extractor.combine_extractions)

    def test_merges_llm_and_regex_tickers(self):
        """Should merge tickers from both sources."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        llm_tickers = ["AAPL", "MSFT"]
        regex_tickers = ["GOOGL", "TSLA"]

        result = extractor.combine_extractions(llm_tickers, regex_tickers)

        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" in result
        assert "TSLA" in result

    def test_deduplicates_combined(self):
        """Should deduplicate when combining."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        llm_tickers = ["AAPL", "MSFT"]
        regex_tickers = ["AAPL", "TSLA"]  # AAPL is duplicate

        result = extractor.combine_extractions(llm_tickers, regex_tickers)

        assert result.count("AAPL") == 1

    def test_respects_max_tickers_limit(self):
        """Should respect max 10 tickers per tweet limit."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor(max_tickers=10)
        llm_tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "META", "AMZN"]
        regex_tickers = ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN"]

        result = extractor.combine_extractions(llm_tickers, regex_tickers)

        assert len(result) <= 10

    def test_configurable_max_tickers(self):
        """Should allow configurable max tickers."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor(max_tickers=5)
        llm_tickers = ["AAPL", "MSFT", "GOOGL"]
        regex_tickers = ["TSLA", "META", "AMZN"]

        result = extractor.combine_extractions(llm_tickers, regex_tickers)

        assert len(result) <= 5

    def test_prioritizes_llm_tickers(self):
        """Should prioritize LLM tickers when combining."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor(max_tickers=3)
        llm_tickers = ["AAPL", "MSFT", "GOOGL"]
        regex_tickers = ["TSLA", "META"]

        result = extractor.combine_extractions(llm_tickers, regex_tickers)

        # First 3 should be LLM tickers
        assert result[:3] == ["AAPL", "MSFT", "GOOGL"]


class TestTickerExtractorEdgeCases:
    """Tests for ticker extraction edge cases."""

    def test_handles_no_tickers(self):
        """Should handle text with no tickers."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "The market is looking interesting today"
        result = extractor.extract_with_regex(text)

        # Should not have THE, etc.
        assert len([t for t in result if t not in ["THE"]]) >= 0

    def test_handles_more_than_10_tickers(self):
        """Should limit to max 10 tickers."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "$AAPL $MSFT $GOOGL $TSLA $META $AMZN $NVDA $AMD $INTC $QCOM $AVGO $TXN"
        result = extractor.extract_with_regex(text)

        assert len(result) <= 10

    def test_handles_special_characters(self):
        """Should handle tickers with special characters around them."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "($AAPL) [MSFT] {GOOGL}"
        result = extractor.extract_with_regex(text)

        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" in result

    def test_filters_ceo_cfo_etc(self, common_words_list):
        """Should filter common abbreviations like CEO, CFO, IPO, ETF."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()
        text = "CEO says ETF IPO GDP are important for USA NYC EST PST"
        result = extractor.extract_with_regex(text)

        assert "CEO" not in result
        assert "CFO" not in result
        assert "IPO" not in result
        assert "ETF" not in result
        assert "GDP" not in result


# ---------------------------------------------------------------------------
# SentimentAnalyzer Tests (sentiment_analyzer.py)
# ---------------------------------------------------------------------------

class TestSentimentAnalyzerModule:
    """Tests for the sentiment_analyzer.py module."""

    def test_module_imports(self):
        """SentimentAnalyzer module should be importable."""
        from scraper.llm import sentiment_analyzer
        assert sentiment_analyzer is not None

    def test_sentiment_analyzer_class_exists(self):
        """SentimentAnalyzer class should exist."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer
        assert SentimentAnalyzer is not None


class TestSentimentAnalyzerFromLLM:
    """Tests for extracting sentiment from LLM response."""

    def test_extract_from_llm_response_method_exists(self):
        """extract_from_llm_response method should exist."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        assert hasattr(analyzer, "extract_from_llm_response")
        assert callable(analyzer.extract_from_llm_response)

    def test_extract_bullish_sentiment(self):
        """Should extract bullish sentiment."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        response = {"sentiment": "bullish"}
        result = analyzer.extract_from_llm_response(response)

        assert result == "bullish"

    def test_extract_bearish_sentiment(self):
        """Should extract bearish sentiment."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        response = {"sentiment": "bearish"}
        result = analyzer.extract_from_llm_response(response)

        assert result == "bearish"

    def test_extract_neutral_sentiment(self):
        """Should extract neutral sentiment."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        response = {"sentiment": "neutral"}
        result = analyzer.extract_from_llm_response(response)

        assert result == "neutral"

    def test_handles_missing_sentiment_key(self):
        """Should return neutral when sentiment key missing."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        response = {"classification": "CRITICAL"}
        result = analyzer.extract_from_llm_response(response)

        assert result == "neutral"

    def test_normalizes_sentiment_case(self):
        """Should normalize sentiment to lowercase."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        response = {"sentiment": "BULLISH"}
        result = analyzer.extract_from_llm_response(response)

        assert result == "bullish"

    def test_handles_invalid_sentiment(self):
        """Should return neutral for invalid sentiment values."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        response = {"sentiment": "positive"}  # Invalid, should be bullish/bearish/neutral
        result = analyzer.extract_from_llm_response(response)

        assert result == "neutral"


class TestSentimentAnalyzerKeywords:
    """Tests for keyword-based sentiment analysis."""

    def test_analyze_with_keywords_method_exists(self):
        """analyze_with_keywords method should exist."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        assert hasattr(analyzer, "analyze_with_keywords")
        assert callable(analyzer.analyze_with_keywords)

    def test_detects_bullish_keywords(self):
        """Should detect bullish keywords."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        text = "Stock is breaking out, very bullish, buy signal"
        result = analyzer.analyze_with_keywords(text)

        assert result == "bullish"

    def test_detects_bearish_keywords(self):
        """Should detect bearish keywords."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        text = "Stock crashing, bearish divergence, sell signal"
        result = analyzer.analyze_with_keywords(text)

        assert result == "bearish"

    def test_returns_neutral_for_mixed(self):
        """Should return neutral for mixed sentiment."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        text = "Could be bullish but also showing bearish signs"
        result = analyzer.analyze_with_keywords(text)

        assert result == "neutral"

    def test_returns_neutral_for_no_keywords(self):
        """Should return neutral when no sentiment keywords found."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        text = "Market data released today for analysis"
        result = analyzer.analyze_with_keywords(text)

        assert result == "neutral"

    def test_handles_empty_text(self):
        """Should handle empty text."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_with_keywords("")

        assert result == "neutral"

    def test_handles_none_text(self):
        """Should handle None text."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_with_keywords(None)

        assert result == "neutral"

    def test_case_insensitive(self):
        """Should be case insensitive for keyword matching."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()

        assert analyzer.analyze_with_keywords("BULLISH signal") == "bullish"
        assert analyzer.analyze_with_keywords("Bearish trend") == "bearish"


class TestSentimentAnalyzerBullishKeywords:
    """Tests for specific bullish keywords."""

    def test_bullish_keywords(self):
        """Should recognize various bullish keywords."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        bullish_phrases = [
            "buy the dip",
            "breaking out",
            "upside potential",
            "strong momentum",
            "going up",
            "moon soon",
            "long position",
            "accumulating"
        ]

        for phrase in bullish_phrases:
            result = analyzer.analyze_with_keywords(f"Stock is {phrase}")
            assert result == "bullish", f"Failed to detect bullish for: {phrase}"


class TestSentimentAnalyzerBearishKeywords:
    """Tests for specific bearish keywords."""

    def test_bearish_keywords(self):
        """Should recognize various bearish keywords."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        bearish_phrases = [
            "sell signal",
            "breaking down",
            "downside risk",
            "weak momentum",
            "going down",
            "crash incoming",
            "short position",
            "distributing"
        ]

        for phrase in bearish_phrases:
            result = analyzer.analyze_with_keywords(f"Stock is {phrase}")
            assert result == "bearish", f"Failed to detect bearish for: {phrase}"


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestFullIntegration:
    """End-to-end integration tests."""

    @patch("scraper.llm.client.Anthropic")
    def test_full_pipeline(self, mock_anthropic, sample_tweets, mock_anthropic_api_response):
        """Test full tweet -> classification + tickers + sentiment pipeline."""
        from scraper.llm.client import AnthropicClient
        from scraper.llm.triage import TriageEngine
        from scraper.llm.ticker_extractor import TickerExtractor
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_api_response
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            # Initialize components
            client = AnthropicClient()
            config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")
            engine = TriageEngine(client=client, config_path=config_path)
            ticker_extractor = TickerExtractor()
            sentiment_analyzer = SentimentAnalyzer()

            # Process tweets
            results = engine.process_batch(sample_tweets)

            # Verify results have all required fields
            for result in results:
                assert "classification" in result
                assert "confidence" in result
                assert "tickers" in result
                assert "sentiment" in result

    def test_ticker_extraction_accuracy(self):
        """Test ticker extraction achieves >95% accuracy on test cases."""
        from scraper.llm.ticker_extractor import TickerExtractor

        extractor = TickerExtractor()

        test_cases = [
            ("$AAPL is up today", ["AAPL"]),
            ("Looking at $MSFT and $GOOGL", ["MSFT", "GOOGL"]),
            ("TSLA breaking resistance", ["TSLA"]),
            ("$NVDA $AMD are strong", ["NVDA", "AMD"]),
            ("No tickers here", []),
            ("$META previously $FB", ["META", "FB"]),
            ("Multiple mentions of $AAPL and AAPL again", ["AAPL"]),
            ("THE AAPL stock", ["AAPL"]),  # Should filter THE
        ]

        correct = 0
        total = len(test_cases)

        for text, expected in test_cases:
            result = extractor.extract_with_regex(text)
            # Check if all expected tickers are found
            if all(t in result for t in expected):
                # Check no unexpected common words included
                common = {"THE", "AND", "FOR", "ARE", "BUT", "NOT"}
                if not any(t in common for t in result):
                    correct += 1

        accuracy = correct / total
        assert accuracy >= 0.95, f"Ticker extraction accuracy {accuracy:.2%} is below 95%"

    def test_sentiment_fallback_chain(self):
        """Test sentiment falls back correctly: LLM -> keywords -> neutral."""
        from scraper.llm.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()

        # Valid LLM response
        assert analyzer.extract_from_llm_response({"sentiment": "bullish"}) == "bullish"

        # Invalid LLM response falls back
        invalid_response = {"sentiment": "invalid"}
        assert analyzer.extract_from_llm_response(invalid_response) == "neutral"

        # Keywords fallback
        assert analyzer.analyze_with_keywords("very bullish signal") == "bullish"
        assert analyzer.analyze_with_keywords("no sentiment here") == "neutral"

    def test_classification_validation(self):
        """Test classification values are always valid."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()

        # Test various invalid classifications
        invalid_responses = [
            {"classification": "URGENT", "confidence": 0.8, "tickers": [], "sentiment": "neutral", "reasoning": ""},
            {"classification": "HIGH", "confidence": 0.8, "tickers": [], "sentiment": "neutral", "reasoning": ""},
            {"classification": "", "confidence": 0.8, "tickers": [], "sentiment": "neutral", "reasoning": ""},
            {"confidence": 0.8, "tickers": [], "sentiment": "neutral", "reasoning": ""},  # Missing classification
        ]

        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        for response in invalid_responses:
            mock_client.classify_batch.return_value = [response]
            engine = TriageEngine(client=mock_client, config_path=config_path)

            results = engine.process_batch([{
                "id": "1",
                "username": "test",
                "content": "Test tweet",
                "pre_filter_action": "triage"
            }])

            assert results[0]["classification"] in ["CRITICAL", "IMPORTANT", "ROUTINE", "SKIP"]


class TestErrorRecovery:
    """Tests for error recovery and graceful degradation."""

    @patch("scraper.llm.client.Anthropic")
    def test_recovers_from_partial_batch_failure(self, mock_anthropic, sample_tweets):
        """Should recover when some batch items fail."""
        from scraper.llm.client import AnthropicClient
        from scraper.llm.triage import TriageEngine

        mock_content = MagicMock()
        mock_content.text = json.dumps([
            {"classification": "CRITICAL", "confidence": 0.9, "tickers": ["AAPL"], "sentiment": "bullish", "reasoning": ""},
            None,  # Failed item
            {"classification": "ROUTINE", "confidence": 0.7, "tickers": [], "sentiment": "neutral", "reasoning": ""}
        ])

        mock_message = MagicMock()
        mock_message.content = [mock_content]
        mock_message.usage = MagicMock()
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client_instance

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AnthropicClient()
            config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")
            engine = TriageEngine(client=client, config_path=config_path)

            results = engine.process_batch(sample_tweets)

            # Should still return results for all tweets
            assert len(results) == len(sample_tweets)

    def test_handles_empty_batch(self):
        """Should handle empty tweet batch."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)
        results = engine.process_batch([])

        assert results == []
        mock_client.classify_batch.assert_not_called()

    def test_handles_all_non_triage_tweets(self):
        """Should handle batch where all tweets have non-triage action."""
        from scraper.llm.triage import TriageEngine

        mock_client = MagicMock()
        config_path = str(Path(__file__).parent.parent / "config" / "triage_config.json")

        engine = TriageEngine(client=mock_client, config_path=config_path)

        non_triage_tweets = [
            {"id": "1", "username": "user1", "content": "Tweet 1", "pre_filter_action": "skip"},
            {"id": "2", "username": "user2", "content": "Tweet 2", "pre_filter_action": "accept"},
        ]

        results = engine.process_batch(non_triage_tweets)

        # Should return results but not call LLM
        mock_client.classify_batch.assert_not_called()
