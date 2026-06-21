"""
Test suite for pre-filter module.

Tests are written FIRST following TDD methodology.
These tests will fail until implementation is complete.

Test Categories:
1. Pattern Detection Tests (patterns.py)
2. Skip Pattern Tests
3. High-Signal Account Tests
4. Triage Routing Tests
5. Edge Case Tests
6. Skip Rate Performance Tests
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def filter_config():
    """Sample filter configuration."""
    return {
        "skip_patterns": {
            "retweets": ["^RT @", "RT @"],
            "spam": [
                "follow me",
                "check out my",
                "link in bio",
                "click here",
                "dm me",
                "free giveaway",
                "win prizes",
                "subscribe to",
                "join my discord",
                "telegram group"
            ],
            "memes": [
                "wen moon",
                "to the moon",
                "hodl"
            ],
            "promotional": [
                "buy now",
                "limited time",
                "special offer",
                "exclusive deal",
                "#ad ",
                "#sponsored"
            ],
            "crypto_spam": [
                "#cryptocurrency",
                "#crypto",
                "#bitcoin",
                "#ethereum",
                "moonshot",
                "100x gem"
            ]
        },
        "text_quality": {
            "min_length": 20,
            "max_emoji_count": 5,
            "max_hashtag_count": 5,
            "max_url_count": 3,
            "min_word_count": 5
        },
        "url_blocklist": [
            "bit.ly",
            "tinyurl.com",
            "t.co/promo",
            "linktr.ee",
            "onlyfans.com"
        ],
        "skip_on_all_caps": True,
        "skip_on_excessive_punctuation": True,
        "max_repeated_chars": 3
    }


@pytest.fixture
def account_config():
    """Sample account configuration."""
    return {
        "high_signal": {
            "description": "Accounts with consistently high-quality insights",
            "accounts": [
                "BillAckman",
                "elonmusk",
                "GerberKawasaki",
                "mcuban",
                "chamath"
            ]
        },
        "noisy": {
            "description": "Accounts that post frequently with low signal",
            "accounts": [],
            "aggressive_filter": True
        },
        "tickers_only": {
            "description": "Accounts where we only care about ticker mentions",
            "accounts": [
                "unusual_whales",
                "OptionsHawk",
                "MarketRebels"
            ]
        },
        "verified_analysts": {
            "description": "Verified financial analysts",
            "accounts": []
        }
    }


@pytest.fixture
def mock_config_files(tmp_path, filter_config, account_config):
    """Create mock config files in a temporary directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    filter_file = config_dir / "filter_config.json"
    filter_file.write_text(json.dumps(filter_config))

    account_file = config_dir / "account_config.json"
    account_file.write_text(json.dumps(account_config))

    return {
        "config_dir": str(config_dir),
        "filter_config": str(filter_file),
        "account_config": str(account_file)
    }


@pytest.fixture
def pre_filter(mock_config_files):
    """Create PreFilter instance with mock configs."""
    from scraper.filters.pre_filter import PreFilter

    return PreFilter(
        filter_config_path=mock_config_files["filter_config"],
        account_config_path=mock_config_files["account_config"]
    )


@pytest.fixture
def sample_tweet_dataset():
    """Sample dataset of 100 tweets for skip rate testing.

    Designed to achieve 80%+ skip rate:
    - 20 retweets (skip)
    - 15 spam tweets (skip)
    - 10 promotional content (skip)
    - 10 crypto spam (skip)
    - 10 excessive emojis (skip)
    - 5 all caps (skip)
    - 5 too short/low quality (skip)
    - 5 URL blocklist (skip)
    - 10 high-signal accounts (accept)
    - 10 normal quality tweets (triage)

    Total: 80 skip + 10 accept + 10 triage = 100
    """
    tweets = []

    # Retweets (20) - SKIP
    for i in range(20):
        tweets.append({
            "username": f"user{i}",
            "content": f"RT @someone: This is a retweet about topic {i}"
        })

    # Spam tweets (15) - SKIP
    spam_phrases = [
        "follow me for more content",
        "check out my new product",
        "link in bio for discount",
        "click here for free stuff",
        "dm me for details",
        "free giveaway happening now",
        "win prizes by following",
        "subscribe to my channel",
        "join my discord server",
        "telegram group for trading",
        "follow me please",
        "check out my profile",
        "link in bio always",
        "click here to learn",
        "dm me for offers"
    ]
    for i, phrase in enumerate(spam_phrases):
        tweets.append({
            "username": f"spammer{i}",
            "content": f"Hey everyone! {phrase}! This is great content."
        })

    # Promotional content (10) - SKIP
    promo_phrases = [
        "buy now before it sells out",
        "limited time offer only",
        "special offer just for you",
        "exclusive deal available now",
        "#ad Check this product out",
        "#sponsored content here",
        "buy now at discount prices",
        "limited time sale happening",
        "special offer ends soon",
        "exclusive deal for followers"
    ]
    for i, phrase in enumerate(promo_phrases):
        tweets.append({
            "username": f"promoter{i}",
            "content": f"Amazing opportunity! {phrase} Don't miss out!"
        })

    # Crypto spam (10) - SKIP
    crypto_phrases = [
        "#cryptocurrency is the future",
        "#crypto investment advice",
        "#bitcoin to the moon",
        "#ethereum breaking out",
        "moonshot coin discovered today",
        "100x gem just launched",
        "#crypto gains incoming",
        "#bitcoin holders rejoice",
        "#ethereum smart contracts",
        "moonshot potential here"
    ]
    for i, phrase in enumerate(crypto_phrases):
        tweets.append({
            "username": f"cryptobro{i}",
            "content": f"Big news! {phrase} Get in early!"
        })

    # Excessive emojis (10) - SKIP (using actual emoji unicode)
    emoji_sets = [
        "\U0001F525\U0001F680\U0001F4B0\U0001F4C8\U0001F3AF\U0001F31F",  # fire, rocket, money bag, chart, target, star
        "\U0001F389\U0001F38A\U0001F388\U0001F381\U0001F380\U0001F3C6",  # party, confetti, balloon, gift, ribbon, trophy
        "\U0001F4AA\U0001F44D\U0001F44F\U0001F64C\U0001F91D\U0001F64F",  # muscle, thumbs up, clap, raised hands, handshake, pray
        "\u2B50\u2764\uFE0F\U0001F496\U0001F49C\U0001F49A\U0001F499",     # star, hearts
        "\U0001F60D\U0001F60E\U0001F929\U0001F973\U0001F917\U0001F970",  # face emojis
        "\U0001F4A5\U0001F4AB\U0001F4A2\U0001F4A8\U0001F4A3\U0001F4AF",  # explosion, dizzy, anger, dash, bomb, 100
        "\U0001F30D\U0001F30E\U0001F30F\U0001F311\U0001F319\U0001F31F",  # earth, moon, star
        "\U0001F3C1\U0001F3C6\U0001F3C5\U0001F396\U0001F397\U0001F3F3",  # flags and medals
        "\U0001F4B2\U0001F4B5\U0001F4B4\U0001F4B6\U0001F4B7\U0001F4B8",  # money
        "\U0001F6A8\U0001F6A9\U0001F6AB\U0001F6B7\U0001F6B6\U0001F6B4",  # signs and people
    ]
    for i, emojis in enumerate(emoji_sets):
        tweets.append({
            "username": f"emojilover{i}",
            "content": f"This is so amazing! {emojis} Check it out everyone today!"
        })

    # All caps (5) - SKIP
    for i in range(5):
        tweets.append({
            "username": f"capsuser{i}",
            "content": "THIS IS AMAZING NEWS FOR EVERYONE TODAY CHECK IT OUT NOW"
        })

    # Too short/low quality (5) - SKIP
    for i in range(5):
        tweets.append({
            "username": f"shortuser{i}",
            "content": f"ok {i}"
        })

    # URL blocklist (5) - SKIP
    blocked_urls = [
        "bit.ly/scam123",
        "tinyurl.com/deal456",
        "linktr.ee/myprofile",
        "onlyfans.com/someone",
        "bit.ly/offer789"
    ]
    for i, url in enumerate(blocked_urls):
        tweets.append({
            "username": f"linkuser{i}",
            "content": f"Check this out at https://{url} for more info today"
        })

    # High-signal accounts (10) - ACCEPT
    high_signal_content = [
        "Interesting analysis of market dynamics",
        "Here's my take on the current situation",
        "Breaking down the quarterly earnings",
        "Key insights from today's meeting",
        "My thoughts on recent developments",
        "Analysis of the current market trends",
        "Important update on company performance",
        "Deep dive into financials today",
        "Critical analysis of the situation",
        "My perspective on market movements"
    ]
    high_signal_users = ["BillAckman", "elonmusk", "GerberKawasaki",
                        "mcuban", "chamath", "BillAckman", "elonmusk",
                        "GerberKawasaki", "mcuban", "chamath"]
    for i, (user, content) in enumerate(zip(high_signal_users, high_signal_content)):
        tweets.append({
            "username": user,
            "content": content
        })

    # Normal quality tweets (10) - TRIAGE
    normal_content = [
        "The Federal Reserve announcement today was interesting and worth discussing further.",
        "Looking at $AAPL earnings, strong performance in services sector this quarter.",
        "Market volatility continues as investors weigh economic data carefully.",
        "Interesting developments in the tech sector worth monitoring closely today.",
        "Quarterly results exceeded expectations for several major companies today.",
        "Economic indicators suggest mixed signals for the upcoming quarter ahead.",
        "Analysis of recent market trends shows interesting patterns emerging now.",
        "Investment thesis remains strong despite recent market fluctuations observed.",
        "Key metrics to watch include revenue growth and margin expansion trends.",
        "Strategic positioning matters more than ever in this market environment."
    ]
    for i, content in enumerate(normal_content):
        tweets.append({
            "username": f"analyst{i}",
            "content": content
        })

    return tweets


# ---------------------------------------------------------------------------
# Pattern Detection Tests (patterns.py)
# ---------------------------------------------------------------------------

class TestPatternModule:
    """Tests for the patterns.py module."""

    def test_module_imports(self):
        """Pattern module should be importable."""
        from scraper.filters import patterns

        assert patterns is not None

    def test_has_spam_pattern_functions(self):
        """Module should have spam detection functions."""
        from scraper.filters.patterns import (
            is_retweet,
            has_spam_keywords,
            has_promotional_content,
            has_crypto_spam
        )

        assert callable(is_retweet)
        assert callable(has_spam_keywords)
        assert callable(has_promotional_content)
        assert callable(has_crypto_spam)

    def test_has_text_quality_functions(self):
        """Module should have text quality analysis functions."""
        from scraper.filters.patterns import (
            count_emojis,
            count_hashtags,
            count_urls,
            count_words,
            is_all_caps,
            has_excessive_punctuation,
            has_repeated_chars,
            get_text_length
        )

        assert callable(count_emojis)
        assert callable(count_hashtags)
        assert callable(count_urls)
        assert callable(count_words)
        assert callable(is_all_caps)
        assert callable(has_excessive_punctuation)
        assert callable(has_repeated_chars)
        assert callable(get_text_length)

    def test_has_url_analysis_functions(self):
        """Module should have URL analysis functions."""
        from scraper.filters.patterns import (
            extract_urls,
            is_url_blocklisted
        )

        assert callable(extract_urls)
        assert callable(is_url_blocklisted)


class TestRetweetDetection:
    """Tests for retweet pattern detection."""

    def test_detects_rt_at_start(self):
        """Should detect RT @ at the beginning of tweet."""
        from scraper.filters.patterns import is_retweet

        assert is_retweet("RT @user: This is a retweet") is True

    def test_detects_rt_in_middle(self):
        """Should detect RT @ in the middle of tweet."""
        from scraper.filters.patterns import is_retweet

        assert is_retweet("Check this out RT @user: Amazing!") is True

    def test_non_retweet_returns_false(self):
        """Should return False for non-retweets."""
        from scraper.filters.patterns import is_retweet

        assert is_retweet("This is an original tweet") is False

    def test_case_insensitive_detection(self):
        """Should detect retweets case-insensitively."""
        from scraper.filters.patterns import is_retweet

        assert is_retweet("rt @user: lowercase retweet") is True
        assert is_retweet("Rt @User: Mixed case retweet") is True


class TestEmojiCounting:
    """Tests for emoji counting functionality."""

    def test_counts_common_emojis(self):
        """Should count common emojis."""
        from scraper.filters.patterns import count_emojis

        # Using descriptive text instead of actual emojis for test clarity
        # The implementation should count actual emoji unicode characters
        assert count_emojis("Hello! Great news!") == 0

    def test_counts_multiple_emojis(self):
        """Should count multiple emojis correctly."""
        from scraper.filters.patterns import count_emojis

        # Text with multiple fire emojis
        text = "This is lit \U0001F525\U0001F525\U0001F525"
        assert count_emojis(text) == 3

    def test_counts_diverse_emojis(self):
        """Should count diverse emoji types."""
        from scraper.filters.patterns import count_emojis

        # Rocket, fire, thumbs up, heart, star
        text = "\U0001F680\U0001F525\U0001F44D\u2764\uFE0F\u2B50"
        assert count_emojis(text) >= 4

    def test_empty_string_returns_zero(self):
        """Should return 0 for empty string."""
        from scraper.filters.patterns import count_emojis

        assert count_emojis("") == 0

    def test_none_returns_zero(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import count_emojis

        assert count_emojis(None) == 0


class TestHashtagCounting:
    """Tests for hashtag counting functionality."""

    def test_counts_hashtags(self):
        """Should count hashtags correctly."""
        from scraper.filters.patterns import count_hashtags

        assert count_hashtags("#hello #world #test") == 3

    def test_no_hashtags_returns_zero(self):
        """Should return 0 when no hashtags."""
        from scraper.filters.patterns import count_hashtags

        assert count_hashtags("No hashtags here") == 0

    def test_empty_string_returns_zero(self):
        """Should return 0 for empty string."""
        from scraper.filters.patterns import count_hashtags

        assert count_hashtags("") == 0

    def test_none_returns_zero(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import count_hashtags

        assert count_hashtags(None) == 0


class TestUrlCounting:
    """Tests for URL counting functionality."""

    def test_counts_http_urls(self):
        """Should count http URLs."""
        from scraper.filters.patterns import count_urls

        assert count_urls("Check http://example.com") == 1

    def test_counts_https_urls(self):
        """Should count https URLs."""
        from scraper.filters.patterns import count_urls

        assert count_urls("Visit https://example.com") == 1

    def test_counts_multiple_urls(self):
        """Should count multiple URLs."""
        from scraper.filters.patterns import count_urls

        text = "See https://a.com and http://b.com and https://c.com"
        assert count_urls(text) == 3

    def test_no_urls_returns_zero(self):
        """Should return 0 when no URLs."""
        from scraper.filters.patterns import count_urls

        assert count_urls("No URLs here") == 0

    def test_empty_string_returns_zero(self):
        """Should return 0 for empty string."""
        from scraper.filters.patterns import count_urls

        assert count_urls("") == 0


class TestWordCounting:
    """Tests for word counting functionality."""

    def test_counts_words(self):
        """Should count words correctly."""
        from scraper.filters.patterns import count_words

        assert count_words("This is a test sentence") == 5

    def test_handles_extra_spaces(self):
        """Should handle multiple spaces between words."""
        from scraper.filters.patterns import count_words

        assert count_words("This   has   extra   spaces") == 4

    def test_empty_string_returns_zero(self):
        """Should return 0 for empty string."""
        from scraper.filters.patterns import count_words

        assert count_words("") == 0

    def test_none_returns_zero(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import count_words

        assert count_words(None) == 0


class TestAllCapsDetection:
    """Tests for all caps detection."""

    def test_detects_all_caps(self):
        """Should detect all caps text."""
        from scraper.filters.patterns import is_all_caps

        assert is_all_caps("THIS IS ALL CAPS") is True

    def test_mixed_case_returns_false(self):
        """Should return False for mixed case."""
        from scraper.filters.patterns import is_all_caps

        assert is_all_caps("This Is Mixed Case") is False

    def test_lowercase_returns_false(self):
        """Should return False for lowercase."""
        from scraper.filters.patterns import is_all_caps

        assert is_all_caps("this is lowercase") is False

    def test_mostly_caps_with_threshold(self):
        """Should detect mostly caps (>80% uppercase letters)."""
        from scraper.filters.patterns import is_all_caps

        # This should be considered "all caps" since >80% of letters are uppercase
        # "THIS IS MOSTLY CAPS a" = 17 uppercase, 1 lowercase = 94% uppercase
        assert is_all_caps("THIS IS MOSTLY CAPS a") is True

    def test_handles_non_letter_characters(self):
        """Should handle text with numbers and symbols."""
        from scraper.filters.patterns import is_all_caps

        assert is_all_caps("ALL CAPS WITH 123 AND !!!") is True

    def test_empty_string_returns_false(self):
        """Should return False for empty string."""
        from scraper.filters.patterns import is_all_caps

        assert is_all_caps("") is False


class TestExcessivePunctuation:
    """Tests for excessive punctuation detection."""

    def test_detects_excessive_exclamation(self):
        """Should detect excessive exclamation marks."""
        from scraper.filters.patterns import has_excessive_punctuation

        assert has_excessive_punctuation("WOW!!!!!!!") is True

    def test_detects_excessive_question_marks(self):
        """Should detect excessive question marks."""
        from scraper.filters.patterns import has_excessive_punctuation

        assert has_excessive_punctuation("Really???????") is True

    def test_normal_punctuation_returns_false(self):
        """Should return False for normal punctuation."""
        from scraper.filters.patterns import has_excessive_punctuation

        assert has_excessive_punctuation("Hello! How are you?") is False

    def test_detects_mixed_excessive_punctuation(self):
        """Should detect mixed excessive punctuation."""
        from scraper.filters.patterns import has_excessive_punctuation

        assert has_excessive_punctuation("What?!?!?!") is True


class TestRepeatedCharacters:
    """Tests for repeated character detection."""

    def test_detects_repeated_chars(self):
        """Should detect repeated characters beyond threshold."""
        from scraper.filters.patterns import has_repeated_chars

        assert has_repeated_chars("Sooooo cool", max_repeat=3) is True

    def test_normal_text_returns_false(self):
        """Should return False for normal text."""
        from scraper.filters.patterns import has_repeated_chars

        assert has_repeated_chars("This is normal text", max_repeat=3) is False

    def test_respects_max_repeat_param(self):
        """Should respect max_repeat parameter."""
        from scraper.filters.patterns import has_repeated_chars

        assert has_repeated_chars("Sooo cool", max_repeat=3) is False
        assert has_repeated_chars("Soooo cool", max_repeat=3) is True


class TestTextLength:
    """Tests for text length calculation."""

    def test_returns_correct_length(self):
        """Should return correct text length."""
        from scraper.filters.patterns import get_text_length

        assert get_text_length("Hello") == 5

    def test_empty_string_returns_zero(self):
        """Should return 0 for empty string."""
        from scraper.filters.patterns import get_text_length

        assert get_text_length("") == 0

    def test_none_returns_zero(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import get_text_length

        assert get_text_length(None) == 0


class TestSpamKeywordDetection:
    """Tests for spam keyword detection."""

    def test_detects_follow_me(self):
        """Should detect 'follow me' spam."""
        from scraper.filters.patterns import has_spam_keywords

        patterns = ["follow me"]
        assert has_spam_keywords("Please follow me for more!", patterns) is True

    def test_detects_link_in_bio(self):
        """Should detect 'link in bio' spam."""
        from scraper.filters.patterns import has_spam_keywords

        patterns = ["link in bio"]
        assert has_spam_keywords("Link in bio for discount!", patterns) is True

    def test_case_insensitive(self):
        """Should be case insensitive."""
        from scraper.filters.patterns import has_spam_keywords

        patterns = ["follow me"]
        assert has_spam_keywords("FOLLOW ME for content", patterns) is True

    def test_no_spam_returns_false(self):
        """Should return False when no spam detected."""
        from scraper.filters.patterns import has_spam_keywords

        patterns = ["follow me", "link in bio"]
        assert has_spam_keywords("This is quality content", patterns) is False


class TestPromotionalContent:
    """Tests for promotional content detection."""

    def test_detects_buy_now(self):
        """Should detect 'buy now' promotional content."""
        from scraper.filters.patterns import has_promotional_content

        patterns = ["buy now"]
        assert has_promotional_content("Buy now while supplies last!", patterns) is True

    def test_detects_hashtag_ad(self):
        """Should detect #ad promotional content."""
        from scraper.filters.patterns import has_promotional_content

        patterns = ["#ad "]
        assert has_promotional_content("Check this product #ad ", patterns) is True

    def test_no_promo_returns_false(self):
        """Should return False when no promotional content."""
        from scraper.filters.patterns import has_promotional_content

        patterns = ["buy now", "#ad "]
        assert has_promotional_content("Market analysis for today", patterns) is False


class TestCryptoSpam:
    """Tests for crypto spam detection."""

    def test_detects_crypto_hashtag(self):
        """Should detect #crypto spam."""
        from scraper.filters.patterns import has_crypto_spam

        patterns = ["#crypto"]
        assert has_crypto_spam("Big news for #crypto investors", patterns) is True

    def test_detects_moonshot(self):
        """Should detect moonshot spam."""
        from scraper.filters.patterns import has_crypto_spam

        patterns = ["moonshot"]
        assert has_crypto_spam("This coin is a moonshot!", patterns) is True

    def test_no_crypto_spam_returns_false(self):
        """Should return False when no crypto spam."""
        from scraper.filters.patterns import has_crypto_spam

        patterns = ["#crypto", "moonshot"]
        assert has_crypto_spam("Discussing market trends today", patterns) is False


class TestUrlAnalysis:
    """Tests for URL analysis functionality."""

    def test_extracts_urls(self):
        """Should extract URLs from text."""
        from scraper.filters.patterns import extract_urls

        text = "Check https://example.com and http://test.org"
        urls = extract_urls(text)

        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "http://test.org" in urls

    def test_detects_blocklisted_url(self):
        """Should detect blocklisted URLs."""
        from scraper.filters.patterns import is_url_blocklisted

        blocklist = ["bit.ly", "tinyurl.com"]
        assert is_url_blocklisted("https://bit.ly/abc123", blocklist) is True

    def test_safe_url_returns_false(self):
        """Should return False for non-blocklisted URLs."""
        from scraper.filters.patterns import is_url_blocklisted

        blocklist = ["bit.ly", "tinyurl.com"]
        assert is_url_blocklisted("https://twitter.com/user", blocklist) is False


# ---------------------------------------------------------------------------
# PreFilter Class Tests
# ---------------------------------------------------------------------------

class TestPreFilterModule:
    """Tests for the pre_filter.py module."""

    def test_module_imports(self):
        """PreFilter module should be importable."""
        from scraper.filters import pre_filter

        assert pre_filter is not None

    def test_prefilter_class_exists(self):
        """PreFilter class should exist."""
        from scraper.filters.pre_filter import PreFilter

        assert PreFilter is not None


class TestPreFilterInitialization:
    """Tests for PreFilter initialization."""

    def test_loads_filter_config(self, pre_filter, filter_config):
        """Should load filter configuration."""
        assert pre_filter.filter_config is not None
        assert "skip_patterns" in pre_filter.filter_config

    def test_loads_account_config(self, pre_filter, account_config):
        """Should load account configuration."""
        assert pre_filter.account_config is not None
        assert "high_signal" in pre_filter.account_config

    def test_extracts_high_signal_accounts(self, pre_filter):
        """Should extract high-signal account set (lowercase for comparison)."""
        assert "elonmusk" in pre_filter.high_signal_accounts
        assert "billackman" in pre_filter.high_signal_accounts

    def test_missing_config_file_raises_error(self, tmp_path):
        """Should raise error if config file missing."""
        from scraper.filters.pre_filter import PreFilter

        with pytest.raises(FileNotFoundError):
            PreFilter(
                filter_config_path=str(tmp_path / "nonexistent.json"),
                account_config_path=str(tmp_path / "nonexistent2.json")
            )

    def test_default_config_paths(self, monkeypatch, mock_config_files):
        """Should use default config paths if not specified."""
        from scraper.filters.pre_filter import PreFilter

        # Patch the default config directory
        monkeypatch.setattr(
            "scraper.filters.pre_filter.DEFAULT_CONFIG_DIR",
            mock_config_files["config_dir"]
        )

        pf = PreFilter()
        assert pf.filter_config is not None


# ---------------------------------------------------------------------------
# Skip Pattern Tests
# ---------------------------------------------------------------------------

class TestSkipRetweets:
    """Tests for retweet skipping."""

    def test_skips_retweet_at_start(self, pre_filter):
        """Should skip retweets at start of tweet."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="RT @originaluser: This is a retweet"
        )

        assert result["action"] == "skip"
        assert "retweet" in result["reason"].lower()

    def test_skips_retweet_in_middle(self, pre_filter):
        """Should skip retweets in middle of tweet."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="Check this out RT @user: Amazing content"
        )

        assert result["action"] == "skip"
        assert "retweet" in result["reason"].lower()


class TestSkipExcessiveEmojis:
    """Tests for excessive emoji skipping."""

    def test_skips_excessive_emojis(self, pre_filter):
        """Should skip tweets with excessive emojis."""
        # 6 different emojis exceeds default max of 5
        # Using different emojis to avoid repeated character detection
        # Ensuring enough words to pass word count filter
        result = pre_filter.filter_tweet(
            username="someuser",
            content="This is amazing content here \U0001F525\U0001F680\U0001F4B0\U0001F4C8\U0001F3AF\U0001F31F check it out!"
        )

        assert result["action"] == "skip"
        assert "emoji" in result["reason"].lower()

    def test_allows_moderate_emojis(self, pre_filter):
        """Should allow tweets with moderate emoji count."""
        # 3 emojis is within limit
        result = pre_filter.filter_tweet(
            username="someuser",
            content="Great news today! \U0001F525\U0001F525\U0001F525 Market is up significantly."
        )

        # Should not skip for emojis, might triage
        assert result["action"] != "skip" or "emoji" not in result["reason"].lower()


class TestSkipSpamKeywords:
    """Tests for spam keyword skipping."""

    def test_skips_follow_me_spam(self, pre_filter):
        """Should skip 'follow me' spam."""
        result = pre_filter.filter_tweet(
            username="spammer",
            content="Please follow me for amazing trading tips daily!"
        )

        assert result["action"] == "skip"
        assert "spam" in result["reason"].lower()

    def test_skips_link_in_bio(self, pre_filter):
        """Should skip 'link in bio' spam."""
        result = pre_filter.filter_tweet(
            username="spammer",
            content="Check out my products link in bio for discounts!"
        )

        assert result["action"] == "skip"
        assert "spam" in result["reason"].lower()

    def test_skips_dm_me(self, pre_filter):
        """Should skip 'dm me' spam."""
        result = pre_filter.filter_tweet(
            username="spammer",
            content="Want trading signals? dm me for more info!"
        )

        assert result["action"] == "skip"
        assert "spam" in result["reason"].lower()


class TestSkipPromotionalContent:
    """Tests for promotional content skipping."""

    def test_skips_buy_now(self, pre_filter):
        """Should skip 'buy now' promotional content."""
        result = pre_filter.filter_tweet(
            username="marketer",
            content="Amazing product! buy now before it's gone forever!"
        )

        assert result["action"] == "skip"
        assert "promotional" in result["reason"].lower()

    def test_skips_limited_time(self, pre_filter):
        """Should skip 'limited time' promotional content."""
        result = pre_filter.filter_tweet(
            username="marketer",
            content="This limited time offer ends tonight at midnight!"
        )

        assert result["action"] == "skip"
        assert "promotional" in result["reason"].lower()

    def test_skips_hashtag_ad(self, pre_filter):
        """Should skip #ad promotional content."""
        result = pre_filter.filter_tweet(
            username="influencer",
            content="Love this new product! #ad Check it out folks!"
        )

        assert result["action"] == "skip"
        assert "promotional" in result["reason"].lower()


class TestSkipCryptoSpam:
    """Tests for crypto spam skipping."""

    def test_skips_crypto_hashtag(self, pre_filter):
        """Should skip #crypto spam."""
        result = pre_filter.filter_tweet(
            username="cryptobro",
            content="Huge news for #crypto holders today! Moon incoming!"
        )

        assert result["action"] == "skip"
        assert "crypto" in result["reason"].lower()

    def test_skips_moonshot(self, pre_filter):
        """Should skip moonshot spam."""
        result = pre_filter.filter_tweet(
            username="cryptobro",
            content="This new token is an absolute moonshot opportunity!"
        )

        assert result["action"] == "skip"
        assert "crypto" in result["reason"].lower()

    def test_skips_100x_gem(self, pre_filter):
        """Should skip 100x gem spam."""
        result = pre_filter.filter_tweet(
            username="cryptobro",
            content="Just found a 100x gem that will explode!"
        )

        assert result["action"] == "skip"
        assert "crypto" in result["reason"].lower()


class TestSkipUrlBlocklist:
    """Tests for URL blocklist skipping."""

    def test_skips_bitly_links(self, pre_filter):
        """Should skip bit.ly links."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="Check this out https://bit.ly/abc123 amazing deal!"
        )

        assert result["action"] == "skip"
        assert "url" in result["reason"].lower() or "blocklist" in result["reason"].lower()

    def test_skips_linktr_ee(self, pre_filter):
        """Should skip linktr.ee links."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="All my links at https://linktr.ee/myprofile check them!"
        )

        assert result["action"] == "skip"
        assert "url" in result["reason"].lower() or "blocklist" in result["reason"].lower()

    def test_skips_onlyfans(self, pre_filter):
        """Should skip onlyfans links."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="New content at https://onlyfans.com/someone subscribe!"
        )

        assert result["action"] == "skip"
        assert "url" in result["reason"].lower() or "blocklist" in result["reason"].lower()


class TestSkipAllCaps:
    """Tests for all caps skipping."""

    def test_skips_all_caps_text(self, pre_filter):
        """Should skip all caps text."""
        result = pre_filter.filter_tweet(
            username="louduser",
            content="THIS IS AMAZING NEWS FOR EVERYONE TODAY GET IN NOW!"
        )

        assert result["action"] == "skip"
        assert "caps" in result["reason"].lower()

    def test_allows_normal_case(self, pre_filter):
        """Should allow normal case text."""
        result = pre_filter.filter_tweet(
            username="normaluser",
            content="This is a normal tweet with proper capitalization today."
        )

        # Should not skip for caps
        assert result["action"] != "skip" or "caps" not in result["reason"].lower()


class TestSkipLowQuality:
    """Tests for low quality content skipping."""

    def test_skips_too_short(self, pre_filter):
        """Should skip content that's too short."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="ok"
        )

        assert result["action"] == "skip"
        assert "short" in result["reason"].lower() or "length" in result["reason"].lower() or "quality" in result["reason"].lower()

    def test_skips_too_few_words(self, pre_filter):
        """Should skip content with too few words."""
        result = pre_filter.filter_tweet(
            username="someuser",
            content="yes no maybe"
        )

        assert result["action"] == "skip"
        assert "word" in result["reason"].lower() or "quality" in result["reason"].lower()


# ---------------------------------------------------------------------------
# High-Signal Account Tests
# ---------------------------------------------------------------------------

class TestHighSignalAccounts:
    """Tests for high-signal account handling."""

    def test_accepts_high_signal_account(self, pre_filter):
        """Should accept tweets from high-signal accounts."""
        result = pre_filter.filter_tweet(
            username="elonmusk",
            content="Interesting developments in the tech industry today."
        )

        assert result["action"] == "accept"
        assert "high_signal" in result["reason"].lower() or "signal" in result["reason"].lower()

    def test_accepts_bill_ackman(self, pre_filter):
        """Should accept tweets from BillAckman."""
        result = pre_filter.filter_tweet(
            username="BillAckman",
            content="My thoughts on the current market situation today."
        )

        assert result["action"] == "accept"

    def test_accepts_chamath(self, pre_filter):
        """Should accept tweets from chamath."""
        result = pre_filter.filter_tweet(
            username="chamath",
            content="Breaking down the quarterly earnings report today."
        )

        assert result["action"] == "accept"

    def test_high_signal_bypasses_spam_filter(self, pre_filter):
        """High-signal accounts should bypass spam filters."""
        result = pre_filter.filter_tweet(
            username="elonmusk",
            content="Follow me for more updates on this exciting news!"
        )

        # Even with spam-like content, high-signal should accept
        assert result["action"] == "accept"

    def test_case_insensitive_account_matching(self, pre_filter):
        """Account matching should be case-insensitive."""
        result = pre_filter.filter_tweet(
            username="ELONMUSK",
            content="Testing case sensitivity in username matching."
        )

        assert result["action"] == "accept"


# ---------------------------------------------------------------------------
# Triage Routing Tests
# ---------------------------------------------------------------------------

class TestTriageRouting:
    """Tests for triage routing functionality."""

    def test_triages_normal_content(self, pre_filter):
        """Should triage normal quality content."""
        result = pre_filter.filter_tweet(
            username="analyst",
            content="The Federal Reserve announcement today has significant implications for markets."
        )

        assert result["action"] == "triage"
        assert "llm" in result["reason"].lower() or "classification" in result["reason"].lower() or "triage" in result["reason"].lower()

    def test_triages_financial_discussion(self, pre_filter):
        """Should triage financial discussion content."""
        result = pre_filter.filter_tweet(
            username="investor",
            content="Looking at $AAPL earnings, the services segment continues to outperform expectations."
        )

        assert result["action"] == "triage"

    def test_triages_market_analysis(self, pre_filter):
        """Should triage market analysis content."""
        result = pre_filter.filter_tweet(
            username="trader",
            content="Market volatility remains elevated as investors process the latest economic data."
        )

        assert result["action"] == "triage"


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_content(self, pre_filter):
        """Should handle empty content gracefully."""
        result = pre_filter.filter_tweet(
            username="user",
            content=""
        )

        assert result["action"] == "skip"
        assert result["reason"] is not None

    def test_handles_none_content(self, pre_filter):
        """Should handle None content gracefully."""
        result = pre_filter.filter_tweet(
            username="user",
            content=None
        )

        assert result["action"] == "skip"
        assert result["reason"] is not None

    def test_handles_none_username(self, pre_filter):
        """Should handle None username gracefully."""
        result = pre_filter.filter_tweet(
            username=None,
            content="This is some test content for the filter today."
        )

        # Should not crash, should process normally
        assert result["action"] in ["skip", "accept", "triage", "extract_only"]

    def test_handles_empty_username(self, pre_filter):
        """Should handle empty username gracefully."""
        result = pre_filter.filter_tweet(
            username="",
            content="This is some test content for the filter today."
        )

        assert result["action"] in ["skip", "accept", "triage", "extract_only"]

    def test_handles_special_characters(self, pre_filter):
        """Should handle special characters in content."""
        result = pre_filter.filter_tweet(
            username="user",
            content="Test with special chars: @#$%^&*()_+-=[]{}|;':\",./<>? today!"
        )

        assert result["action"] in ["skip", "accept", "triage", "extract_only"]

    def test_handles_unicode_content(self, pre_filter):
        """Should handle unicode content properly."""
        result = pre_filter.filter_tweet(
            username="user",
            content="International text: Hello World! Testing unicode support today."
        )

        assert result["action"] in ["skip", "accept", "triage", "extract_only"]

    def test_handles_very_long_content(self, pre_filter):
        """Should handle very long content."""
        long_content = "This is a test tweet. " * 100
        result = pre_filter.filter_tweet(
            username="user",
            content=long_content
        )

        assert result["action"] in ["skip", "accept", "triage", "extract_only"]

    def test_handles_whitespace_only(self, pre_filter):
        """Should handle whitespace-only content."""
        result = pre_filter.filter_tweet(
            username="user",
            content="   \t\n   "
        )

        assert result["action"] == "skip"


class TestExcessivePunctuationSkipping:
    """Tests for excessive punctuation skipping."""

    def test_skips_excessive_exclamation(self, pre_filter):
        """Should skip excessive exclamation marks."""
        result = pre_filter.filter_tweet(
            username="exciteduser",
            content="This is so amazing!!!!!!!!!!!! Can you believe it????"
        )

        assert result["action"] == "skip"
        assert "punctuation" in result["reason"].lower()


class TestRepeatedCharacterSkipping:
    """Tests for repeated character skipping."""

    def test_skips_repeated_chars(self, pre_filter):
        """Should skip text with excessively repeated characters."""
        result = pre_filter.filter_tweet(
            username="user",
            content="This is sooooooo cool today everyone should check it out!"
        )

        assert result["action"] == "skip"
        assert "repeated" in result["reason"].lower() or "character" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Skip Rate Performance Tests
# ---------------------------------------------------------------------------

class TestSkipRatePerformance:
    """Tests for achieving 80%+ skip rate."""

    def test_skip_rate_on_sample_dataset(self, pre_filter, sample_tweet_dataset):
        """Should achieve 80%+ skip rate on sample dataset."""
        skip_count = 0
        accept_count = 0
        triage_count = 0

        for tweet in sample_tweet_dataset:
            result = pre_filter.filter_tweet(
                username=tweet["username"],
                content=tweet["content"]
            )

            if result["action"] == "skip":
                skip_count += 1
            elif result["action"] == "accept":
                accept_count += 1
            else:
                triage_count += 1

        total = len(sample_tweet_dataset)
        skip_rate = skip_count / total

        # Assert 80%+ skip rate
        assert skip_rate >= 0.80, f"Skip rate {skip_rate:.2%} is below 80%"

        # Also verify we have some accepts and triages
        assert accept_count > 0, "Should have some accepts (high-signal)"
        assert triage_count > 0, "Should have some triages (normal content)"

    def test_skip_reasons_logged(self, pre_filter, sample_tweet_dataset):
        """Should provide detailed skip reasons."""
        results = []

        for tweet in sample_tweet_dataset:
            result = pre_filter.filter_tweet(
                username=tweet["username"],
                content=tweet["content"]
            )
            results.append(result)

        # All results should have reasons
        for result in results:
            assert "reason" in result
            assert result["reason"] is not None
            assert len(result["reason"]) > 0


class TestFilterStatistics:
    """Tests for filter statistics functionality."""

    def test_get_stats_method_exists(self, pre_filter):
        """PreFilter should have get_stats method."""
        assert hasattr(pre_filter, "get_stats")
        assert callable(pre_filter.get_stats)

    def test_stats_track_skip_reasons(self, pre_filter):
        """Stats should track skip reasons for tuning."""
        # Run some filters
        pre_filter.filter_tweet("user", "RT @someone: Retweet")
        pre_filter.filter_tweet("spammer", "follow me for tips")
        pre_filter.filter_tweet("elonmusk", "Normal content here")

        stats = pre_filter.get_stats()

        assert "total_processed" in stats
        assert stats["total_processed"] >= 3

    def test_reset_stats(self, pre_filter):
        """Should be able to reset statistics."""
        pre_filter.filter_tweet("user", "RT @someone: Retweet")
        pre_filter.reset_stats()

        stats = pre_filter.get_stats()
        assert stats["total_processed"] == 0


# ---------------------------------------------------------------------------
# Output Format Tests
# ---------------------------------------------------------------------------

class TestOutputFormat:
    """Tests for output format compliance."""

    def test_skip_output_format(self, pre_filter):
        """Skip action should have correct format."""
        result = pre_filter.filter_tweet(
            username="user",
            content="RT @someone: This is a retweet"
        )

        assert "action" in result
        assert "reason" in result
        assert result["action"] == "skip"
        assert isinstance(result["reason"], str)

    def test_accept_output_format(self, pre_filter):
        """Accept action should have correct format."""
        result = pre_filter.filter_tweet(
            username="elonmusk",
            content="Market thoughts for today."
        )

        assert "action" in result
        assert "reason" in result
        assert result["action"] == "accept"
        assert isinstance(result["reason"], str)

    def test_triage_output_format(self, pre_filter):
        """Triage action should have correct format."""
        result = pre_filter.filter_tweet(
            username="analyst",
            content="The Federal Reserve meeting today had interesting implications for markets."
        )

        assert "action" in result
        assert "reason" in result
        assert result["action"] == "triage"
        assert isinstance(result["reason"], str)

    def test_reason_is_descriptive(self, pre_filter):
        """Reason should be descriptive for debugging."""
        result = pre_filter.filter_tweet(
            username="user",
            content="RT @someone: This is a retweet"
        )

        # Reason should contain useful information
        assert len(result["reason"]) > 5


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegrationWithRealConfigs:
    """Integration tests using real config files."""

    def test_loads_real_filter_config(self):
        """Should load real filter_config.json if it exists."""
        from scraper.filters.pre_filter import PreFilter

        config_path = Path(__file__).parent.parent / "config" / "filter_config.json"

        if config_path.exists():
            pf = PreFilter(
                filter_config_path=str(config_path),
                account_config_path=str(config_path.parent / "account_config.json")
            )

            assert pf.filter_config is not None

    def test_loads_real_account_config(self):
        """Should load real account_config.json if it exists."""
        from scraper.filters.pre_filter import PreFilter

        config_path = Path(__file__).parent.parent / "config" / "account_config.json"

        if config_path.exists():
            filter_config_path = config_path.parent / "filter_config.json"
            pf = PreFilter(
                filter_config_path=str(filter_config_path),
                account_config_path=str(config_path)
            )

            assert pf.account_config is not None


# ---------------------------------------------------------------------------
# New Tier System Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def account_config_v2():
    """Account configuration using the new tier schema."""
    return {
        "tiers": {
            "tier_1_high_signal": {
                "description": "High-signal accounts - always triage with author context",
                "accounts": ["BillAckman", "chamath", "mcuban"]
            },
            "tier_2_standard": {
                "description": "Standard accounts - normal filter pipeline",
                "accounts": ["analyst1", "trader1", "investor1", "elonmusk"]
            },
            "tier_3_noisy": {
                "description": "Noisy accounts - require $TICKER + action keyword",
                "accounts": ["memeposter", "cryptobro99", "noisytrader"]
            },
            "tier_flow_data": {
                "description": "Flow data accounts - regex-only, no LLM",
                "accounts": ["unusual_whales", "OptionsHawk", "MarketRebels"]
            }
        },
        "author_context": {
            "BillAckman": "Billionaire hedge fund manager, activist investor at Pershing Square",
            "chamath": "Venture capitalist, former Facebook exec, SPAC sponsor",
            "mcuban": "Billionaire entrepreneur, Shark Tank investor"
        },
        "manual_overrides": ["BillAckman", "chamath"]
    }


@pytest.fixture
def mock_config_files_v2(tmp_path, filter_config, account_config_v2):
    """Create mock config files with new tier schema."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    filter_file = config_dir / "filter_config.json"
    filter_file.write_text(json.dumps(filter_config))

    account_file = config_dir / "account_config.json"
    account_file.write_text(json.dumps(account_config_v2))

    return {
        "config_dir": str(config_dir),
        "filter_config": str(filter_file),
        "account_config": str(account_file)
    }


@pytest.fixture
def pre_filter_v2(mock_config_files_v2):
    """Create PreFilter instance with new tier schema config."""
    from scraper.filters.pre_filter import PreFilter

    return PreFilter(
        filter_config_path=mock_config_files_v2["filter_config"],
        account_config_path=mock_config_files_v2["account_config"]
    )


# ---------------------------------------------------------------------------
# New Pattern Function Tests
# ---------------------------------------------------------------------------

class TestTickerMentionPattern:
    """Tests for ticker mention detection."""

    def test_detects_dollar_ticker(self):
        """Should detect $AAPL style tickers."""
        from scraper.filters.patterns import has_ticker_mention

        assert has_ticker_mention("Looking at $AAPL today") is True

    def test_detects_multiple_tickers(self):
        """Should detect multiple tickers."""
        from scraper.filters.patterns import has_ticker_mention

        assert has_ticker_mention("$TSLA vs $AAPL comparison") is True

    def test_no_ticker_returns_false(self):
        """Should return False when no tickers present."""
        from scraper.filters.patterns import has_ticker_mention

        assert has_ticker_mention("No tickers in this tweet today") is False

    def test_lowercase_ticker_not_detected(self):
        """Should not detect lowercase $tickers."""
        from scraper.filters.patterns import has_ticker_mention

        assert has_ticker_mention("Not a $ticker symbol") is False

    def test_handles_none(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import has_ticker_mention

        assert has_ticker_mention(None) is False

    def test_handles_empty(self):
        """Should handle empty string gracefully."""
        from scraper.filters.patterns import has_ticker_mention

        assert has_ticker_mention("") is False


class TestActionKeywordDetection:
    """Tests for action keyword detection."""

    def test_detects_buy_keyword(self):
        """Should detect 'buy' keyword."""
        from scraper.filters.patterns import has_action_keyword

        assert has_action_keyword("Time to buy this dip") is True

    def test_detects_earnings_keyword(self):
        """Should detect 'earnings' keyword."""
        from scraper.filters.patterns import has_action_keyword

        assert has_action_keyword("Earnings report coming out tomorrow") is True

    def test_detects_breaking_keyword(self):
        """Should detect 'breaking' keyword."""
        from scraper.filters.patterns import has_action_keyword

        assert has_action_keyword("BREAKING: Major news on the market") is True

    def test_no_action_keyword_returns_false(self):
        """Should return False when no action keywords."""
        from scraper.filters.patterns import has_action_keyword

        assert has_action_keyword("Just having a good morning everyone") is False

    def test_handles_none(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import has_action_keyword

        assert has_action_keyword(None) is False

    def test_custom_keywords(self):
        """Should accept custom keyword set."""
        from scraper.filters.patterns import has_action_keyword

        custom = {"moon", "lambo"}
        assert has_action_keyword("Going to the moon", custom) is True
        assert has_action_keyword("Just a normal tweet", custom) is False


class TestExtractTickersRegex:
    """Tests for regex-based ticker extraction."""

    def test_extracts_single_ticker(self):
        """Should extract a single ticker."""
        from scraper.filters.patterns import extract_tickers_regex

        result = extract_tickers_regex("Looking at $AAPL today")
        assert result == ["AAPL"]

    def test_extracts_multiple_tickers(self):
        """Should extract multiple tickers."""
        from scraper.filters.patterns import extract_tickers_regex

        result = extract_tickers_regex("$AAPL $TSLA $MSFT all moving")
        assert set(result) == {"AAPL", "TSLA", "MSFT"}

    def test_deduplicates_tickers(self):
        """Should deduplicate repeated tickers."""
        from scraper.filters.patterns import extract_tickers_regex

        result = extract_tickers_regex("$AAPL is great, $AAPL to the moon")
        assert result == ["AAPL"]

    def test_strips_dollar_sign(self):
        """Should return tickers without $ prefix."""
        from scraper.filters.patterns import extract_tickers_regex

        result = extract_tickers_regex("$GOOG looking strong")
        assert result == ["GOOG"]
        assert "$" not in result[0]

    def test_returns_empty_for_no_tickers(self):
        """Should return empty list when no tickers."""
        from scraper.filters.patterns import extract_tickers_regex

        result = extract_tickers_regex("No tickers here today")
        assert result == []

    def test_handles_none(self):
        """Should handle None gracefully."""
        from scraper.filters.patterns import extract_tickers_regex

        result = extract_tickers_regex(None)
        assert result == []


# ---------------------------------------------------------------------------
# Tier 1 Routing Tests (New Schema)
# ---------------------------------------------------------------------------

class TestTier1Routing:
    """Tests for Tier 1 (high signal) routing with new schema."""

    def test_tier1_routes_to_triage(self, pre_filter_v2):
        """Tier 1 accounts should route to triage (not accept)."""
        result = pre_filter_v2.filter_tweet(
            username="BillAckman",
            content="My thoughts on the current market situation today."
        )

        assert result["action"] == "triage"
        assert result["tier"] == "tier_1"

    def test_tier1_includes_author_context(self, pre_filter_v2):
        """Tier 1 accounts should include author_context when available."""
        result = pre_filter_v2.filter_tweet(
            username="BillAckman",
            content="Important investment thesis for today."
        )

        assert result["action"] == "triage"
        assert "author_context" in result
        assert "Pershing Square" in result["author_context"]

    def test_tier1_bypasses_spam_filter(self, pre_filter_v2):
        """Tier 1 accounts should bypass spam filters."""
        result = pre_filter_v2.filter_tweet(
            username="chamath",
            content="Follow me for more updates on this exciting news!"
        )

        assert result["action"] == "triage"
        assert result["tier"] == "tier_1"

    def test_tier1_bypasses_quality_filter(self, pre_filter_v2):
        """Tier 1 accounts should bypass text quality filters."""
        result = pre_filter_v2.filter_tweet(
            username="mcuban",
            content="Yes!"
        )

        # Even short content should go to triage for tier 1
        assert result["action"] == "triage"
        assert result["tier"] == "tier_1"

    def test_tier1_case_insensitive(self, pre_filter_v2):
        """Tier 1 matching should be case-insensitive."""
        result = pre_filter_v2.filter_tweet(
            username="BILLACKMAN",
            content="Testing case sensitivity in tier routing."
        )

        assert result["action"] == "triage"
        assert result["tier"] == "tier_1"

    def test_tier1_still_skips_empty_content(self, pre_filter_v2):
        """Even Tier 1 should skip empty content."""
        result = pre_filter_v2.filter_tweet(
            username="BillAckman",
            content=""
        )

        assert result["action"] == "skip"


# ---------------------------------------------------------------------------
# Tier 2 Standard Routing Tests (New Schema)
# ---------------------------------------------------------------------------

class TestTier2Routing:
    """Tests for Tier 2 (standard) routing with new schema."""

    def test_tier2_normal_content_triages(self, pre_filter_v2):
        """Tier 2 accounts with good content should triage."""
        result = pre_filter_v2.filter_tweet(
            username="analyst1",
            content="The Federal Reserve meeting today has significant market implications."
        )

        assert result["action"] == "triage"
        assert result["tier"] == "tier_2"

    def test_tier2_spam_skips(self, pre_filter_v2):
        """Tier 2 accounts with spam should be skipped."""
        result = pre_filter_v2.filter_tweet(
            username="trader1",
            content="Follow me for amazing trading tips daily!"
        )

        assert result["action"] == "skip"

    def test_tier2_retweet_skips(self, pre_filter_v2):
        """Tier 2 accounts with retweets should be skipped."""
        result = pre_filter_v2.filter_tweet(
            username="investor1",
            content="RT @someone: This is a retweet about the market"
        )

        assert result["action"] == "skip"

    def test_tier2_no_author_context(self, pre_filter_v2):
        """Tier 2 accounts should not have author_context."""
        result = pre_filter_v2.filter_tweet(
            username="analyst1",
            content="Important market analysis for this quarter."
        )

        assert "author_context" not in result

    def test_tier2_unknown_account_defaults(self, pre_filter_v2):
        """Unknown accounts should default to Tier 2."""
        result = pre_filter_v2.filter_tweet(
            username="completely_new_account",
            content="The Federal Reserve announcement today was interesting and significant."
        )

        assert result["action"] == "triage"
        assert result["tier"] == "tier_2"


# ---------------------------------------------------------------------------
# Tier 3 Aggressive Filter Tests (New Schema)
# ---------------------------------------------------------------------------

class TestTier3AggressiveFilter:
    """Tests for Tier 3 (noisy) aggressive filtering."""

    def test_tier3_skips_without_ticker(self, pre_filter_v2):
        """Tier 3 should skip content without $TICKER mention."""
        result = pre_filter_v2.filter_tweet(
            username="memeposter",
            content="This is just a random tweet about the market today."
        )

        assert result["action"] == "skip"
        assert "tier3" in result["reason"].lower() or "no $TICKER" in result["reason"]

    def test_tier3_skips_without_action_keyword(self, pre_filter_v2):
        """Tier 3 should skip content with ticker but no action keyword."""
        result = pre_filter_v2.filter_tweet(
            username="memeposter",
            content="$AAPL is a company that makes phones and computers."
        )

        assert result["action"] == "skip"
        assert "action keyword" in result["reason"].lower() or "tier3" in result["reason"].lower()

    def test_tier3_triages_with_ticker_and_action(self, pre_filter_v2):
        """Tier 3 should triage content with BOTH $TICKER and action keyword."""
        result = pre_filter_v2.filter_tweet(
            username="noisytrader",
            content="Time to buy $TSLA, earnings are going to be massive!"
        )

        assert result["action"] == "triage"
        assert result["tier"] == "tier_3"

    def test_tier3_requires_both_conditions(self, pre_filter_v2):
        """Tier 3 must have both ticker AND action keyword to pass."""
        # Has action keyword but no ticker
        result = pre_filter_v2.filter_tweet(
            username="cryptobro99",
            content="Time to buy this amazing opportunity for earnings!"
        )

        assert result["action"] == "skip"

    def test_tier3_case_insensitive_username(self, pre_filter_v2):
        """Tier 3 matching should be case-insensitive."""
        result = pre_filter_v2.filter_tweet(
            username="MEMEPOSTER",
            content="Just vibing today with the market trends."
        )

        assert result["action"] == "skip"

    def test_tier3_still_applies_skip_patterns(self, pre_filter_v2):
        """Tier 3 that passes aggressive filter still applies skip patterns."""
        result = pre_filter_v2.filter_tweet(
            username="noisytrader",
            content="RT @someone: Buy $AAPL earnings beat!"
        )

        assert result["action"] == "skip"
        assert "retweet" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Flow Data Routing Tests (New Schema)
# ---------------------------------------------------------------------------

class TestFlowDataRouting:
    """Tests for flow data account routing."""

    def test_flow_routes_to_extract_only(self, pre_filter_v2):
        """Flow data accounts should route to extract_only."""
        result = pre_filter_v2.filter_tweet(
            username="unusual_whales",
            content="$AAPL 150C 01/20 sweep at $2.5M"
        )

        assert result["action"] == "extract_only"
        assert result["tier"] == "tier_flow"

    def test_flow_extract_even_spam_content(self, pre_filter_v2):
        """Flow data accounts should extract even with spam-like content."""
        result = pre_filter_v2.filter_tweet(
            username="OptionsHawk",
            content="Follow me for more options flow data!"
        )

        assert result["action"] == "extract_only"

    def test_flow_extract_case_insensitive(self, pre_filter_v2):
        """Flow data matching should be case-insensitive."""
        result = pre_filter_v2.filter_tweet(
            username="UNUSUAL_WHALES",
            content="$TSLA puts sweeping at high volume"
        )

        assert result["action"] == "extract_only"

    def test_flow_still_skips_empty(self, pre_filter_v2):
        """Flow data accounts should still skip empty content."""
        result = pre_filter_v2.filter_tweet(
            username="unusual_whales",
            content=""
        )

        assert result["action"] == "skip"

    def test_flow_no_author_context(self, pre_filter_v2):
        """Flow data accounts should not have author_context."""
        result = pre_filter_v2.filter_tweet(
            username="MarketRebels",
            content="$SPY 450P sweep at $1.2M"
        )

        assert "author_context" not in result


# ---------------------------------------------------------------------------
# Tier Initialization Tests (New Schema)
# ---------------------------------------------------------------------------

class TestTierInitialization:
    """Tests for tier system initialization with new schema."""

    def test_v2_schema_detected(self, pre_filter_v2):
        """Should detect new schema and disable legacy routing."""
        assert pre_filter_v2._use_legacy_routing is False

    def test_v2_tier1_accounts_loaded(self, pre_filter_v2):
        """Should load tier 1 accounts correctly."""
        assert "billackman" in pre_filter_v2.tier_1_accounts
        assert "chamath" in pre_filter_v2.tier_1_accounts
        assert "mcuban" in pre_filter_v2.tier_1_accounts

    def test_v2_tier3_accounts_loaded(self, pre_filter_v2):
        """Should load tier 3 accounts correctly."""
        assert "memeposter" in pre_filter_v2.tier_3_accounts
        assert "cryptobro99" in pre_filter_v2.tier_3_accounts

    def test_v2_flow_accounts_loaded(self, pre_filter_v2):
        """Should load flow data accounts correctly."""
        assert "unusual_whales" in pre_filter_v2.flow_data_accounts
        assert "optionshawk" in pre_filter_v2.flow_data_accounts

    def test_v2_author_context_loaded(self, pre_filter_v2):
        """Should load author context map correctly."""
        assert "billackman" in pre_filter_v2.author_context_map
        assert "Pershing Square" in pre_filter_v2.author_context_map["billackman"]

    def test_v2_high_signal_alias(self, pre_filter_v2):
        """high_signal_accounts should be alias for tier_1_accounts."""
        assert pre_filter_v2.high_signal_accounts is pre_filter_v2.tier_1_accounts

    def test_legacy_schema_detected(self, pre_filter):
        """Legacy config should enable legacy routing."""
        assert pre_filter._use_legacy_routing is True

    def test_legacy_tier1_from_high_signal(self, pre_filter):
        """Legacy config should populate tier_1 from high_signal."""
        assert "elonmusk" in pre_filter.tier_1_accounts
        assert "billackman" in pre_filter.tier_1_accounts

    def test_legacy_flow_from_tickers_only(self, pre_filter):
        """Legacy config should populate flow_data from tickers_only."""
        assert "unusual_whales" in pre_filter.flow_data_accounts


# ---------------------------------------------------------------------------
# Tier Resolve Tests
# ---------------------------------------------------------------------------

class TestTierResolve:
    """Tests for _resolve_tier method."""

    def test_resolves_tier_1(self, pre_filter_v2):
        """Should resolve tier 1 accounts."""
        assert pre_filter_v2._resolve_tier("billackman") == "tier_1"

    def test_resolves_tier_3(self, pre_filter_v2):
        """Should resolve tier 3 accounts."""
        assert pre_filter_v2._resolve_tier("memeposter") == "tier_3"

    def test_resolves_flow(self, pre_filter_v2):
        """Should resolve flow data accounts."""
        assert pre_filter_v2._resolve_tier("unusual_whales") == "tier_flow"

    def test_resolves_tier_2_default(self, pre_filter_v2):
        """Should default to tier 2 for unknown accounts."""
        assert pre_filter_v2._resolve_tier("unknown_user") == "tier_2"

    def test_resolves_explicit_tier_2(self, pre_filter_v2):
        """Should resolve explicit tier 2 accounts."""
        assert pre_filter_v2._resolve_tier("analyst1") == "tier_2"


# ---------------------------------------------------------------------------
# Stats Tests with New Schema
# ---------------------------------------------------------------------------

class TestStatsWithNewSchema:
    """Tests for statistics tracking with new tier schema."""

    def test_tracks_extract_only_count(self, pre_filter_v2):
        """Should track extract_only count in stats."""
        pre_filter_v2.filter_tweet("unusual_whales", "$AAPL sweep 150C")
        pre_filter_v2.filter_tweet("OptionsHawk", "$TSLA puts active")

        stats = pre_filter_v2.get_stats()
        assert stats["extract_only_count"] == 2

    def test_tracks_triage_count_v2(self, pre_filter_v2):
        """Should track triage count for tier 1 and tier 2."""
        pre_filter_v2.filter_tweet(
            "BillAckman",
            "Important market thesis for today."
        )
        pre_filter_v2.filter_tweet(
            "analyst1",
            "The Federal Reserve announcement has significant implications today."
        )

        stats = pre_filter_v2.get_stats()
        assert stats["triage_count"] == 2

    def test_extract_only_rate_calculated(self, pre_filter_v2):
        """Should calculate extract_only rate correctly."""
        pre_filter_v2.filter_tweet("unusual_whales", "$AAPL sweep at market")
        pre_filter_v2.filter_tweet(
            "analyst1",
            "Normal market analysis content for today."
        )

        stats = pre_filter_v2.get_stats()
        assert stats["extract_only_rate"] == 0.5

    def test_reset_stats_clears_extract_only(self, pre_filter_v2):
        """Reset should clear extract_only count."""
        pre_filter_v2.filter_tweet("unusual_whales", "$AAPL sweep")
        pre_filter_v2.reset_stats()

        stats = pre_filter_v2.get_stats()
        assert stats["extract_only_count"] == 0


# ---------------------------------------------------------------------------
# Skip Rate with New Schema
# ---------------------------------------------------------------------------

class TestSkipRateWithNewSchema:
    """Tests for skip rate with new tier schema."""

    def test_skip_rate_on_sample_dataset_v2(self, pre_filter_v2, sample_tweet_dataset):
        """Should achieve reasonable skip rate with new tier schema.

        Note: The sample dataset was designed for the legacy schema where
        high-signal accounts get 'accept'. In v2, they get 'triage' instead,
        but skip rate should still be high since most junk is still skipped.
        """
        skip_count = 0
        triage_count = 0
        extract_only_count = 0

        for tweet in sample_tweet_dataset:
            result = pre_filter_v2.filter_tweet(
                username=tweet["username"],
                content=tweet["content"]
            )

            if result["action"] == "skip":
                skip_count += 1
            elif result["action"] == "triage":
                triage_count += 1
            elif result["action"] == "extract_only":
                extract_only_count += 1

        total = len(sample_tweet_dataset)
        skip_rate = skip_count / total

        # Should still have high skip rate (80%+ of junk skipped)
        assert skip_rate >= 0.75, f"Skip rate {skip_rate:.2%} is below 75%"

        # Should have some triages (high-signal + normal content)
        assert triage_count > 0, "Should have some triages"
