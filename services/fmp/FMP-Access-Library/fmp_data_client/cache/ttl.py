"""Cache TTL (Time To Live) policies for different data types."""

from datetime import timedelta
from enum import Enum


class CachePolicy(str, Enum):
    """Cache policy types."""

    PERMANENT = "permanent"  # Never expires (historical data)
    LONG = "long"  # 24 hours
    MEDIUM = "medium"  # 6 hours
    SHORT = "short"  # 1 hour
    VERY_SHORT = "very_short"  # 15 minutes
    NONE = "none"  # No caching


# TTL durations for each policy
POLICY_DURATIONS = {
    CachePolicy.PERMANENT: None,  # Never expires
    CachePolicy.LONG: timedelta(hours=24),
    CachePolicy.MEDIUM: timedelta(hours=6),
    CachePolicy.SHORT: timedelta(hours=1),
    CachePolicy.VERY_SHORT: timedelta(minutes=15),
    CachePolicy.NONE: None,  # Don't cache
}


# Data type to cache policy mapping
DATA_TYPE_POLICIES = {
    # Real-time data - very short TTL
    "quote": CachePolicy.VERY_SHORT,
    "aftermarket_quote": CachePolicy.VERY_SHORT,

    # Company profile - long TTL (changes infrequently)
    "profile": CachePolicy.LONG,
    "executives": CachePolicy.LONG,

    # Historical events - permanent (historical data doesn't change)
    "dividends": CachePolicy.PERMANENT,
    "splits": CachePolicy.PERMANENT,

    # Earnings calendar - short TTL (updates frequently)
    "earnings_calendar": CachePolicy.SHORT,

    # Fundamental statements - permanent for past periods
    "income_statements": CachePolicy.PERMANENT,
    "balance_sheets": CachePolicy.PERMANENT,
    "cash_flow_statements": CachePolicy.PERMANENT,

    # Metrics and ratios - long TTL
    "key_metrics": CachePolicy.LONG,
    "financial_ratios": CachePolicy.LONG,
    "financial_scores": CachePolicy.LONG,

    # Valuation - medium TTL
    "dcf_valuation": CachePolicy.MEDIUM,
    "enterprise_values": CachePolicy.LONG,

    # Analyst data - short TTL (updates frequently)
    "analyst_estimates": CachePolicy.SHORT,
    "price_targets": CachePolicy.SHORT,
    "price_target_summary": CachePolicy.SHORT,
    "analyst_grades": CachePolicy.SHORT,

    # Ownership - medium TTL (updated quarterly)
    "institutional_holders": CachePolicy.MEDIUM,
    "insider_trades": CachePolicy.SHORT,

    # Historical prices - permanent
    "historical_prices": CachePolicy.PERMANENT,

    # Transcripts - permanent (historical)
    "transcripts": CachePolicy.PERMANENT,
    "transcript_summaries": CachePolicy.PERMANENT,

    # SEC filings - permanent (historical)
    "sec_filings": CachePolicy.PERMANENT,
    "filing_summaries": CachePolicy.PERMANENT,

    # News - short TTL
    "news": CachePolicy.SHORT,

    # Analysis results - medium TTL
    "institutional_analysis": CachePolicy.MEDIUM,
}


def get_cache_policy(data_type: str) -> CachePolicy:
    """Get cache policy for a data type.

    Args:
        data_type: Type of data

    Returns:
        Cache policy enum value
    """
    return DATA_TYPE_POLICIES.get(data_type, CachePolicy.MEDIUM)


def get_ttl_duration(data_type: str) -> timedelta | None:
    """Get TTL duration for a data type.

    Args:
        data_type: Type of data

    Returns:
        Timedelta for TTL or None if permanent/no-cache
    """
    policy = get_cache_policy(data_type)
    return POLICY_DURATIONS.get(policy)


def should_cache(data_type: str) -> bool:
    """Check if a data type should be cached.

    Args:
        data_type: Type of data

    Returns:
        True if data should be cached
    """
    policy = get_cache_policy(data_type)
    return policy != CachePolicy.NONE
