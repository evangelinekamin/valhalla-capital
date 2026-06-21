"""
Pattern detection module for pre-filtering tweets.

Provides regex patterns and helper functions for:
- Spam detection (retweets, spam keywords, promotional content)
- Text quality metrics (length, word count, emoji count)
- URL analysis (blocklist checking, excessive URLs)
- All caps detection
- Excessive punctuation detection
- Repeated character detection
"""

import re
from typing import List, Optional


# ---------------------------------------------------------------------------
# Regex Pattern Constants
# ---------------------------------------------------------------------------

# Retweet patterns
RT_PATTERN = re.compile(r"RT\s+@", re.IGNORECASE)

# URL extraction pattern
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")

# Hashtag pattern
HASHTAG_PATTERN = re.compile(r"#\w+")

# Emoji pattern - covers most common emoji ranges
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U00002300-\U000023FF"  # Miscellaneous Technical
    "\U00002600-\U000026FF"  # Miscellaneous Symbols
    "\U00002700-\U000027BF"  # Dingbats
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0001F1E0-\U0001F1FF"  # Flags (iOS)
    "\u2764"                  # Heart
    "\u2B50"                  # Star
    "]+",
    flags=re.UNICODE
)

# Excessive punctuation pattern (4+ consecutive punctuation marks)
EXCESSIVE_PUNCTUATION_PATTERN = re.compile(r"[!?]{4,}|[!?]{2,}[!?]{2,}")

# Repeated character pattern (4+ of the same letter in a row)
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{3,}", re.IGNORECASE)

# Ticker mention pattern: $AAPL, $TSLA (1-5 uppercase letters preceded by $)
TICKER_MENTION_PATTERN = re.compile(r"\$[A-Z]{1,5}\b")

# Action keywords for aggressive pre-filter (Tier 3 noisy accounts)
ACTION_KEYWORDS = {
    "buy", "sell", "long", "short", "calls", "puts",
    "earnings", "revenue", "upgrade", "downgrade",
    "target", "price target", "guidance", "forecast",
    "beat", "miss", "dividend", "buyback", "split",
    "acquisition", "merger", "ipo", "sec filing",
    "fda", "approval", "recall", "investigation",
    "breaking", "alert", "halt", "resume",
    "overweight", "underweight", "outperform",
}


# ---------------------------------------------------------------------------
# Retweet Detection
# ---------------------------------------------------------------------------

def is_retweet(text: Optional[str]) -> bool:
    """
    Check if text is a retweet.

    Args:
        text: Tweet content to check

    Returns:
        True if text contains retweet pattern (RT @)
    """
    if not text:
        return False
    return bool(RT_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Emoji Functions
# ---------------------------------------------------------------------------

def count_emojis(text: Optional[str]) -> int:
    """
    Count the number of emojis in text.

    Args:
        text: Text to analyze

    Returns:
        Number of emoji characters found
    """
    if not text:
        return 0
    # Find all emoji matches
    matches = EMOJI_PATTERN.findall(text)
    # Each match can be multiple emojis, count total characters
    total = sum(len(m) for m in matches)
    return total


# ---------------------------------------------------------------------------
# Hashtag Functions
# ---------------------------------------------------------------------------

def count_hashtags(text: Optional[str]) -> int:
    """
    Count the number of hashtags in text.

    Args:
        text: Text to analyze

    Returns:
        Number of hashtags found
    """
    if not text:
        return 0
    return len(HASHTAG_PATTERN.findall(text))


# ---------------------------------------------------------------------------
# URL Functions
# ---------------------------------------------------------------------------

def count_urls(text: Optional[str]) -> int:
    """
    Count the number of URLs in text.

    Args:
        text: Text to analyze

    Returns:
        Number of URLs found
    """
    if not text:
        return 0
    return len(URL_PATTERN.findall(text))


def extract_urls(text: Optional[str]) -> List[str]:
    """
    Extract all URLs from text.

    Args:
        text: Text to analyze

    Returns:
        List of URL strings found
    """
    if not text:
        return []
    return URL_PATTERN.findall(text)


def is_url_blocklisted(url: str, blocklist: List[str]) -> bool:
    """
    Check if a URL matches any blocklist entry.

    Args:
        url: URL to check
        blocklist: List of blocklist patterns/domains

    Returns:
        True if URL matches any blocklist entry
    """
    if not url or not blocklist:
        return False
    url_lower = url.lower()
    for blocked in blocklist:
        if blocked.lower() in url_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Word Functions
# ---------------------------------------------------------------------------

def count_words(text: Optional[str]) -> int:
    """
    Count the number of words in text.

    Args:
        text: Text to analyze

    Returns:
        Number of words found
    """
    if not text:
        return 0
    # Split on whitespace and filter empty strings
    words = [w for w in text.split() if w]
    return len(words)


# ---------------------------------------------------------------------------
# Text Length Functions
# ---------------------------------------------------------------------------

def get_text_length(text: Optional[str]) -> int:
    """
    Get the length of text.

    Args:
        text: Text to measure

    Returns:
        Length of text (0 if None)
    """
    if text is None:
        return 0
    return len(text)


# ---------------------------------------------------------------------------
# All Caps Detection
# ---------------------------------------------------------------------------

def is_all_caps(text: Optional[str]) -> bool:
    """
    Check if text is mostly uppercase (>80% of letters are uppercase).

    Args:
        text: Text to check

    Returns:
        True if more than 80% of letters are uppercase
    """
    if not text:
        return False

    # Extract only alphabetic characters
    letters = [c for c in text if c.isalpha()]

    if len(letters) < 5:  # Need at least 5 letters to judge
        return False

    uppercase_count = sum(1 for c in letters if c.isupper())
    uppercase_ratio = uppercase_count / len(letters)

    return uppercase_ratio > 0.80


# ---------------------------------------------------------------------------
# Excessive Punctuation Detection
# ---------------------------------------------------------------------------

def has_excessive_punctuation(text: Optional[str]) -> bool:
    """
    Check if text has excessive punctuation marks.

    Excessive is defined as 4+ consecutive punctuation marks
    (like !!!! or ????) or mixed patterns (like ?!?!?!)

    Args:
        text: Text to check

    Returns:
        True if excessive punctuation is found
    """
    if not text:
        return False
    return bool(EXCESSIVE_PUNCTUATION_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Repeated Character Detection
# ---------------------------------------------------------------------------

def has_repeated_chars(text: Optional[str], max_repeat: int = 3) -> bool:
    """
    Check if text has excessively repeated characters.

    Args:
        text: Text to check
        max_repeat: Maximum allowed consecutive repetitions (default 3)

    Returns:
        True if characters are repeated more than max_repeat times
    """
    if not text:
        return False

    # Build pattern dynamically based on max_repeat
    pattern = re.compile(r"(.)\1{" + str(max_repeat) + r",}", re.IGNORECASE)
    return bool(pattern.search(text))


# ---------------------------------------------------------------------------
# Spam Keyword Detection
# ---------------------------------------------------------------------------

def has_spam_keywords(text: Optional[str], patterns: List[str]) -> bool:
    """
    Check if text contains any spam keywords.

    Args:
        text: Text to check
        patterns: List of spam keyword patterns to match

    Returns:
        True if any spam pattern is found
    """
    if not text or not patterns:
        return False

    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Promotional Content Detection
# ---------------------------------------------------------------------------

def has_promotional_content(text: Optional[str], patterns: List[str]) -> bool:
    """
    Check if text contains promotional content.

    Args:
        text: Text to check
        patterns: List of promotional patterns to match

    Returns:
        True if any promotional pattern is found
    """
    if not text or not patterns:
        return False

    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Crypto Spam Detection
# ---------------------------------------------------------------------------

def has_crypto_spam(text: Optional[str], patterns: List[str]) -> bool:
    """
    Check if text contains crypto spam patterns.

    Args:
        text: Text to check
        patterns: List of crypto spam patterns to match

    Returns:
        True if any crypto spam pattern is found
    """
    if not text or not patterns:
        return False

    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Text Quality Analysis
# ---------------------------------------------------------------------------

def analyze_text_quality(
    text: Optional[str],
    min_length: int = 20,
    min_word_count: int = 5,
    max_emoji_count: int = 5,
    max_hashtag_count: int = 5,
    max_url_count: int = 3
) -> dict:
    """
    Analyze overall text quality.

    Args:
        text: Text to analyze
        min_length: Minimum required length
        min_word_count: Minimum required word count
        max_emoji_count: Maximum allowed emoji count
        max_hashtag_count: Maximum allowed hashtag count
        max_url_count: Maximum allowed URL count

    Returns:
        Dictionary with quality metrics and pass/fail status
    """
    length = get_text_length(text)
    word_count = count_words(text)
    emoji_count = count_emojis(text)
    hashtag_count = count_hashtags(text)
    url_count = count_urls(text)

    issues = []

    if length < min_length:
        issues.append(f"too_short (length={length}, min={min_length})")

    if word_count < min_word_count:
        issues.append(f"too_few_words (words={word_count}, min={min_word_count})")

    if emoji_count > max_emoji_count:
        issues.append(f"excessive_emojis (count={emoji_count}, max={max_emoji_count})")

    if hashtag_count > max_hashtag_count:
        issues.append(f"excessive_hashtags (count={hashtag_count}, max={max_hashtag_count})")

    if url_count > max_url_count:
        issues.append(f"excessive_urls (count={url_count}, max={max_url_count})")

    return {
        "length": length,
        "word_count": word_count,
        "emoji_count": emoji_count,
        "hashtag_count": hashtag_count,
        "url_count": url_count,
        "issues": issues,
        "passes": len(issues) == 0
    }


# ---------------------------------------------------------------------------
# Tier 3 Aggressive Pre-Filter Helpers
# ---------------------------------------------------------------------------

def has_ticker_mention(text: Optional[str]) -> bool:
    """Check if text contains a $TICKER mention."""
    if not text:
        return False
    return bool(TICKER_MENTION_PATTERN.search(text))


def has_action_keyword(text: Optional[str], keywords: Optional[set] = None) -> bool:
    """Check if text contains any financial action keyword."""
    if not text:
        return False
    if keywords is None:
        keywords = ACTION_KEYWORDS
    text_lower = text.lower()
    for keyword in keywords:
        if keyword in text_lower:
            return True
    return False


def extract_tickers_regex(text: Optional[str]) -> List[str]:
    """Extract $TICKER symbols from text using regex only (for flow data tier)."""
    if not text:
        return []
    matches = TICKER_MENTION_PATTERN.findall(text)
    # Strip the $ prefix and deduplicate while preserving order
    tickers = list(dict.fromkeys(m.lstrip("$") for m in matches))
    return tickers
