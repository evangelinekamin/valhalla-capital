"""
Pre-filter module for rule-based tweet filtering.

Implements tier-aware routing to achieve 80%+ LLM cost reduction:
- SKIP: Retweets, spam patterns, low quality content
- TRIAGE: Content that needs LLM classification (with optional author_context)
- EXTRACT_ONLY: Flow data accounts (regex extraction, no LLM)

Tier routing:
- Tier 1 (high signal): Bypass skip/quality filters, triage with author_context + boost
- Tier 2 (standard):    Standard skip patterns -> quality check -> triage
- Tier 3 (noisy):       Aggressive pre-filter (require $TICKER + action keyword)
- Flow data:            Skip LLM entirely, regex-only extraction

Expected output format:
{
    'action': 'skip' | 'triage' | 'extract_only',
    'reason': str,
    'tier': str,            # tier_1, tier_2, tier_3, tier_flow
    'author_context': str   # only for tier_1 accounts (optional)
}
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from . import patterns

# Configure logger
logger = logging.getLogger(__name__)

# Default config directory (relative to this file's parent)
DEFAULT_CONFIG_DIR = str(Path(__file__).parent.parent / "config")


class PreFilter:
    """
    Rule-based pre-filter for Twitter content with tier-aware routing.

    Implements four-tier routing:
    - Tier 1 (high signal): Always triage with author_context, bypass spam filters
    - Tier 2 (standard): Standard skip patterns + quality checks -> triage
    - Tier 3 (noisy): Aggressive pre-filter requiring $TICKER + action keyword
    - Flow data: Extract tickers/numbers with regex only, no LLM

    Attributes:
        filter_config: Configuration for skip patterns and text quality rules
        account_config: Configuration for account categorization
        tier_1_accounts: Set of tier 1 usernames (lowercase)
        tier_3_accounts: Set of tier 3 usernames (lowercase)
        flow_data_accounts: Set of flow data usernames (lowercase)
        author_context_map: Dict mapping lowercase username -> context string
        high_signal_accounts: Alias for tier_1_accounts (backward compat)
        stats: Dictionary tracking filter statistics
    """

    def __init__(
        self,
        filter_config_path: Optional[str] = None,
        account_config_path: Optional[str] = None
    ):
        """
        Initialize PreFilter with configuration files.

        Args:
            filter_config_path: Path to filter_config.json (default: auto-detect)
            account_config_path: Path to account_config.json (default: auto-detect)

        Raises:
            FileNotFoundError: If config files cannot be found
        """
        # Set default paths if not provided
        if filter_config_path is None:
            filter_config_path = str(Path(DEFAULT_CONFIG_DIR) / "filter_config.json")
        if account_config_path is None:
            account_config_path = str(Path(DEFAULT_CONFIG_DIR) / "account_config.json")

        # Load configurations
        self.filter_config = self._load_config(filter_config_path)
        self.account_config = self._load_config(account_config_path)

        # Build tier lookup maps (case-insensitive)
        self._build_tier_lookups()

        # Initialize statistics tracking
        self._stats = {
            "total_processed": 0,
            "skip_count": 0,
            "accept_count": 0,
            "triage_count": 0,
            "extract_only_count": 0,
            "skip_reasons": {}
        }

        logger.info(
            f"PreFilter initialized: "
            f"T1={len(self.tier_1_accounts)}, "
            f"T3={len(self.tier_3_accounts)}, "
            f"Flow={len(self.flow_data_accounts)}"
        )

    def _load_config(self, path: str) -> dict:
        """
        Load configuration from JSON file.

        Args:
            path: Path to config file

        Returns:
            Parsed JSON configuration

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file isn't valid JSON
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_tier_lookups(self) -> None:
        """
        Build tier lookup sets from account_config.

        Supports both the new 'tiers' schema and the legacy flat schema
        for backward compatibility with existing tests.
        """
        # Check if this is the new schema (has 'tiers' key) or legacy
        if "tiers" in self.account_config:
            tiers = self.account_config["tiers"]

            self.tier_1_accounts: Set[str] = {
                a.lower() for a in tiers.get("tier_1_high_signal", {}).get("accounts", [])
            }
            self.tier_3_accounts: Set[str] = {
                a.lower() for a in tiers.get("tier_3_noisy", {}).get("accounts", [])
            }
            self.flow_data_accounts: Set[str] = {
                a.lower() for a in tiers.get("tier_flow_data", {}).get("accounts", [])
            }

            # Author context map (case-insensitive keys)
            raw_context = self.account_config.get("author_context", {})
            self.author_context_map: Dict[str, str] = {
                k.lower(): v for k, v in raw_context.items()
            }

            # Use new tier-aware routing
            self._use_legacy_routing = False
        else:
            # Legacy schema fallback (for backward compat with existing tests)
            self.tier_1_accounts = {
                a.lower() for a in self.account_config.get("high_signal", {}).get("accounts", [])
            }
            self.tier_3_accounts: Set[str] = set()
            self.flow_data_accounts = {
                a.lower() for a in self.account_config.get("tickers_only", {}).get("accounts", [])
            }
            self.author_context_map: Dict[str, str] = {}

            # Use legacy routing (accept for high_signal)
            self._use_legacy_routing = True

        # Backward compat alias
        self.high_signal_accounts = self.tier_1_accounts

    def _resolve_tier(self, username_lower: str) -> str:
        """
        Resolve which tier a username belongs to.

        Args:
            username_lower: Lowercase username

        Returns:
            Tier string: tier_1, tier_2, tier_3, or tier_flow
        """
        if username_lower in self.tier_1_accounts:
            return "tier_1"
        if username_lower in self.tier_3_accounts:
            return "tier_3"
        if username_lower in self.flow_data_accounts:
            return "tier_flow"
        return "tier_2"

    def filter_tweet(self, username: Optional[str], content: Optional[str]) -> Dict[str, str]:
        """
        Filter a single tweet and determine routing action.

        Args:
            username: Twitter username (without @)
            content: Tweet content/text

        Returns:
            Dictionary with keys:
            - action: 'skip', 'triage', or 'extract_only'
            - reason: Detailed explanation for debugging
            - tier: Account tier (tier_1, tier_2, tier_3, tier_flow)
            - author_context: Context string (only for tier_1, optional)
        """
        self._stats["total_processed"] += 1

        # Handle edge cases first
        if content is None or content.strip() == "":
            return self._skip("empty_content: Content is empty or None")

        # Normalize username for comparison
        username_lower = username.lower() if username else ""

        # Legacy routing for old config schema (backward compat with tests)
        if self._use_legacy_routing:
            return self._filter_tweet_legacy(username_lower, username, content)

        # Determine tier
        tier = self._resolve_tier(username_lower)

        # === TIER FLOW DATA: Skip LLM, regex-only extraction ===
        if tier == "tier_flow":
            return self._extract_only(
                f"flow_data_account: {username}",
                tier=tier
            )

        # === TIER 3 NOISY: Aggressive pre-filter ===
        if tier == "tier_3":
            has_ticker = patterns.has_ticker_mention(content)
            has_action = patterns.has_action_keyword(content)
            if not (has_ticker and has_action):
                reason_parts = []
                if not has_ticker:
                    reason_parts.append("no $TICKER mention")
                if not has_action:
                    reason_parts.append("no action keyword")
                return self._skip(
                    f"tier3_aggressive_filter: {', '.join(reason_parts)} ({username})"
                )
            # Passed aggressive filter -- fall through to standard skip checks then triage

        # === TIER 1: Bypass skip/quality filters, go straight to triage ===
        if tier == "tier_1":
            author_context = self.author_context_map.get(username_lower)
            return self._triage(
                f"tier_routed: tier_1 ({username})",
                tier=tier,
                author_context=author_context
            )

        # === Common skip patterns (applies to T2 and T3 that passed aggressive filter) ===
        skip_result = self._check_skip_patterns(content)
        if skip_result:
            return skip_result

        # === Text quality ===
        quality_result = self._check_text_quality(content)
        if quality_result:
            return quality_result

        # === Route to triage ===
        return self._triage(
            f"tier_routed: {tier} ({username})",
            tier=tier
        )

    def _filter_tweet_legacy(self, username_lower: str, username: Optional[str], content: str) -> Dict[str, str]:
        """
        Legacy routing for old config schema. Preserves original behavior
        where high_signal accounts get action='accept'.

        Args:
            username_lower: Lowercase username
            username: Original username
            content: Tweet content
        """
        # Priority 1: Check high-signal accounts (bypass all filters)
        if username_lower in self.high_signal_accounts:
            return self._accept(f"high_signal_account: {username}")

        # Priority 2: Check skip patterns
        skip_result = self._check_skip_patterns(content)
        if skip_result:
            return skip_result

        # Priority 3: Check text quality
        quality_result = self._check_text_quality(content)
        if quality_result:
            return quality_result

        # Default: Triage for LLM classification
        return self._triage("needs_llm_classification: Content passed pre-filters")

    def _check_skip_patterns(self, content: str) -> Optional[Dict[str, str]]:
        """
        Check content against skip patterns.

        Args:
            content: Tweet content to check

        Returns:
            Skip result dict if pattern matched, None otherwise
        """
        skip_patterns = self.filter_config.get("skip_patterns", {})

        # Check retweets
        retweet_patterns = skip_patterns.get("retweets", [])
        if patterns.is_retweet(content):
            return self._skip("retweet: Content is a retweet (RT @)")

        # Check spam keywords
        spam_patterns = skip_patterns.get("spam", [])
        if patterns.has_spam_keywords(content, spam_patterns):
            matched = self._find_matched_pattern(content, spam_patterns)
            return self._skip(f"spam_keyword: Matched spam pattern '{matched}'")

        # Check promotional content
        promo_patterns = skip_patterns.get("promotional", [])
        if patterns.has_promotional_content(content, promo_patterns):
            matched = self._find_matched_pattern(content, promo_patterns)
            return self._skip(f"promotional_content: Matched promo pattern '{matched}'")

        # Check crypto spam
        crypto_patterns = skip_patterns.get("crypto_spam", [])
        if patterns.has_crypto_spam(content, crypto_patterns):
            matched = self._find_matched_pattern(content, crypto_patterns)
            return self._skip(f"crypto_spam: Matched crypto pattern '{matched}'")

        # Check meme patterns
        meme_patterns = skip_patterns.get("memes", [])
        if patterns.has_spam_keywords(content, meme_patterns):
            matched = self._find_matched_pattern(content, meme_patterns)
            return self._skip(f"meme_content: Matched meme pattern '{matched}'")

        # Check URL blocklist
        url_blocklist = self.filter_config.get("url_blocklist", [])
        urls = patterns.extract_urls(content)
        for url in urls:
            if patterns.is_url_blocklisted(url, url_blocklist):
                matched = self._find_matched_pattern(url, url_blocklist)
                return self._skip(f"blocklisted_url: URL matches blocklist '{matched}'")

        # Check all caps
        if self.filter_config.get("skip_on_all_caps", True):
            if patterns.is_all_caps(content):
                return self._skip("all_caps: Content is mostly uppercase")

        # Check excessive punctuation
        if self.filter_config.get("skip_on_excessive_punctuation", True):
            if patterns.has_excessive_punctuation(content):
                return self._skip("excessive_punctuation: Too many punctuation marks")

        # Check repeated characters
        max_repeated = self.filter_config.get("max_repeated_chars", 3)
        if patterns.has_repeated_chars(content, max_repeated):
            return self._skip("repeated_characters: Excessively repeated characters")

        return None

    def _check_text_quality(self, content: str) -> Optional[Dict[str, str]]:
        """
        Check content text quality metrics.

        Args:
            content: Tweet content to check

        Returns:
            Skip result dict if quality fails, None otherwise
        """
        quality_config = self.filter_config.get("text_quality", {})

        min_length = quality_config.get("min_length", 20)
        min_word_count = quality_config.get("min_word_count", 5)
        max_emoji_count = quality_config.get("max_emoji_count", 5)
        max_hashtag_count = quality_config.get("max_hashtag_count", 5)
        max_url_count = quality_config.get("max_url_count", 3)

        # Check length
        text_length = patterns.get_text_length(content)
        if text_length < min_length:
            return self._skip(
                f"low_quality_short: Content too short "
                f"(length={text_length}, min={min_length})"
            )

        # Check word count
        word_count = patterns.count_words(content)
        if word_count < min_word_count:
            return self._skip(
                f"low_quality_words: Too few words "
                f"(words={word_count}, min={min_word_count})"
            )

        # Check emoji count
        emoji_count = patterns.count_emojis(content)
        if emoji_count > max_emoji_count:
            return self._skip(
                f"excessive_emojis: Too many emojis "
                f"(count={emoji_count}, max={max_emoji_count})"
            )

        # Check hashtag count
        hashtag_count = patterns.count_hashtags(content)
        if hashtag_count > max_hashtag_count:
            return self._skip(
                f"excessive_hashtags: Too many hashtags "
                f"(count={hashtag_count}, max={max_hashtag_count})"
            )

        # Check URL count
        url_count = patterns.count_urls(content)
        if url_count > max_url_count:
            return self._skip(
                f"excessive_urls: Too many URLs "
                f"(count={url_count}, max={max_url_count})"
            )

        return None

    def _find_matched_pattern(self, text: str, pattern_list: List[str]) -> str:
        """
        Find which pattern was matched in text.

        Args:
            text: Text that matched
            pattern_list: List of patterns to check

        Returns:
            First matched pattern or "unknown"
        """
        text_lower = text.lower()
        for pattern in pattern_list:
            if pattern.lower() in text_lower:
                return pattern
        return "unknown"

    def _skip(self, reason: str) -> Dict[str, str]:
        """
        Create skip result and update stats.

        Args:
            reason: Reason for skipping

        Returns:
            Skip result dictionary
        """
        self._stats["skip_count"] += 1

        # Track skip reasons for tuning
        reason_key = reason.split(":")[0]  # Get reason category
        if reason_key not in self._stats["skip_reasons"]:
            self._stats["skip_reasons"][reason_key] = 0
        self._stats["skip_reasons"][reason_key] += 1

        logger.debug(f"SKIP: {reason}")
        return {"action": "skip", "reason": reason}

    def _accept(self, reason: str) -> Dict[str, str]:
        """
        Create accept result and update stats.
        Used only in legacy routing mode.

        Args:
            reason: Reason for accepting

        Returns:
            Accept result dictionary
        """
        self._stats["accept_count"] += 1
        logger.debug(f"ACCEPT: {reason}")
        return {"action": "accept", "reason": reason}

    def _triage(
        self,
        reason: str,
        tier: str = "tier_2",
        author_context: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Create triage result and update stats.

        Args:
            reason: Reason for triaging
            tier: Account tier
            author_context: Optional author context for LLM prompt

        Returns:
            Triage result dictionary with tier and optional author_context
        """
        self._stats["triage_count"] += 1
        logger.debug(f"TRIAGE: {reason}")
        result = {"action": "triage", "reason": reason, "tier": tier}
        if author_context:
            result["author_context"] = author_context
        return result

    def _extract_only(self, reason: str, tier: str = "tier_flow") -> Dict[str, str]:
        """
        Create extract_only result and update stats.

        Args:
            reason: Reason for extract-only routing
            tier: Account tier

        Returns:
            Extract-only result dictionary
        """
        self._stats["extract_only_count"] += 1
        logger.debug(f"EXTRACT_ONLY: {reason}")
        return {"action": "extract_only", "reason": reason, "tier": tier}

    def get_stats(self) -> Dict:
        """
        Get current filter statistics.

        Returns:
            Dictionary with filter statistics including:
            - total_processed: Total tweets processed
            - skip_count: Number skipped
            - accept_count: Number accepted (legacy only)
            - triage_count: Number triaged
            - extract_only_count: Number routed to extract-only
            - skip_reasons: Breakdown of skip reasons
            - skip_rate: Percentage of tweets skipped
        """
        stats = dict(self._stats)
        total = stats["total_processed"]
        if total > 0:
            stats["skip_rate"] = stats["skip_count"] / total
            stats["accept_rate"] = stats["accept_count"] / total
            stats["triage_rate"] = stats["triage_count"] / total
            stats["extract_only_rate"] = stats["extract_only_count"] / total
        else:
            stats["skip_rate"] = 0.0
            stats["accept_rate"] = 0.0
            stats["triage_rate"] = 0.0
            stats["extract_only_rate"] = 0.0
        return stats

    def reset_stats(self) -> None:
        """Reset filter statistics to zero."""
        self._stats = {
            "total_processed": 0,
            "skip_count": 0,
            "accept_count": 0,
            "triage_count": 0,
            "extract_only_count": 0,
            "skip_reasons": {}
        }
        logger.info("Filter statistics reset")

    def log_stats_summary(self) -> None:
        """Log a summary of filter statistics."""
        stats = self.get_stats()
        logger.info(
            f"PreFilter Stats: "
            f"Total={stats['total_processed']}, "
            f"Skip={stats['skip_count']} ({stats['skip_rate']:.1%}), "
            f"Accept={stats['accept_count']} ({stats['accept_rate']:.1%}), "
            f"Triage={stats['triage_count']} ({stats['triage_rate']:.1%}), "
            f"ExtractOnly={stats['extract_only_count']} ({stats['extract_only_rate']:.1%})"
        )
        if stats["skip_reasons"]:
            logger.info(f"Skip Reasons: {stats['skip_reasons']}")
