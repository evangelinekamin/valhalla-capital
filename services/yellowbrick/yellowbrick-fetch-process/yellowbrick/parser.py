"""
Parser for Yellowbrick JSON pitch data.

Converts raw JSON from Yellowbrick API/embedded data into Pitch models.
All functions are pure and never mutate their inputs.

IMPORTANT: This module follows immutability principles:
- Input data is never modified
- New objects are always returned
- Failed parses are skipped, not raised
"""

import logging
from decimal import Decimal
from typing import Any

from yellowbrick.models import Pitch

logger = logging.getLogger(__name__)


def determine_pitch_type(sentiment: str | None) -> str:
    """
    Determine pitch type from sentiment value.

    Args:
        sentiment: Raw sentiment string from JSON (bullish, bearish, neutral, etc.)

    Returns:
        Normalized pitch type string: 'bullish', 'bearish', or 'neutral'
    """
    if sentiment is None:
        return "neutral"

    sentiment_lower = str(sentiment).strip().lower()

    if sentiment_lower == "bullish":
        return "bullish"
    elif sentiment_lower == "bearish":
        return "bearish"
    else:
        return "neutral"


def determine_author_type(author_data: dict[str, Any]) -> str | None:
    """
    Determine author type from author data.

    Args:
        author_data: Author object from JSON

    Returns:
        'professional', 'retail', or None if unknown
    """
    if not author_data:
        return None

    is_professional = author_data.get("isProfessional")

    if is_professional is None:
        return None

    return "professional" if is_professional else "retail"


def extract_company_data(company: dict[str, Any]) -> dict[str, Any]:
    """
    Extract company data from nested JSON structure.

    Args:
        company: Company object from JSON

    Returns:
        Flattened dict with company data fields
    """
    if not company:
        return {}

    result: dict[str, Any] = {}

    # Direct company fields
    if company.get("companyName"):
        result["company_name"] = company["companyName"]

    if company.get("tickerSymbol"):
        result["ticker_symbol"] = company["tickerSymbol"]

    if company.get("simpleIndustryDescription"):
        result["sector"] = company["simpleIndustryDescription"]

    if company.get("exchangeSymbol"):
        result["exchange"] = company["exchangeSymbol"]

    if company.get("currencyCode"):
        result["currency"] = company["currencyCode"]

    if company.get("isoCountryCode"):
        result["country"] = company["isoCountryCode"]

    if company.get("businessDescription"):
        result["business_description"] = company["businessDescription"]

    # Nested companyData fields
    company_data = company.get("companyData", {})
    if company_data:
        if company_data.get("lastCloseMarketCap") is not None:
            result["market_cap"] = company_data["lastCloseMarketCap"]

        if company_data.get("lastClosePrice") is not None:
            result["current_price"] = company_data["lastClosePrice"]

        if company_data.get("lastClosePriceEarnings") is not None:
            result["pe_ratio"] = company_data["lastClosePriceEarnings"]

        if company_data.get("lastCloseTevEbitda") is not None:
            result["ev_ebitda"] = company_data["lastCloseTevEbitda"]

        if company_data.get("lastClosePriceBookValue") is not None:
            result["pb_ratio"] = company_data["lastClosePriceBookValue"]

        if company_data.get("averageVolume") is not None:
            result["average_volume"] = company_data["averageVolume"]

        if company_data.get("totalRevenues") is not None:
            result["total_revenues"] = company_data["totalRevenues"]

        if company_data.get("ebitda") is not None:
            result["ebitda"] = company_data["ebitda"]

        if company_data.get("grossProfit") is not None:
            result["gross_profit"] = company_data["grossProfit"]

        if company_data.get("operatingIncome") is not None:
            result["operating_income"] = company_data["operatingIncome"]

        if company_data.get("cashAndEquivalents") is not None:
            result["cash"] = company_data["cashAndEquivalents"]

        if company_data.get("totalDebt") is not None:
            result["total_debt"] = company_data["totalDebt"]

        if company_data.get("totalEquity") is not None:
            result["total_equity"] = company_data["totalEquity"]

        if company_data.get("returnOnEquityPercent") is not None:
            result["roe_percent"] = company_data["returnOnEquityPercent"]

        if company_data.get("lastClose52WeekHigh") is not None:
            result["52_week_high"] = company_data["lastClose52WeekHigh"]

        if company_data.get("lastClose52WeekLow") is not None:
            result["52_week_low"] = company_data["lastClose52WeekLow"]

    return result


def extract_returns_data(returns: dict[str, Any]) -> dict[str, Any]:
    """
    Extract returns data from nested JSON structure.

    Args:
        returns: Returns object from JSON

    Returns:
        Flattened dict with returns data fields
    """
    if not returns:
        return {}

    result: dict[str, Any] = {}

    if returns.get("originalPrice") is not None:
        result["original_price"] = returns["originalPrice"]

    if returns.get("currentPrice") is not None:
        result["current_price"] = returns["currentPrice"]

    if returns.get("currentReturn") is not None:
        result["current_return"] = returns["currentReturn"]

    if returns.get("oneMonthReturn") is not None:
        result["one_month_return"] = returns["oneMonthReturn"]

    if returns.get("threeMonthReturn") is not None:
        result["three_month_return"] = returns["threeMonthReturn"]

    if returns.get("sixMonthReturn") is not None:
        result["six_month_return"] = returns["sixMonthReturn"]

    if returns.get("oneYearReturn") is not None:
        result["one_year_return"] = returns["oneYearReturn"]

    if returns.get("twoYearReturn") is not None:
        result["two_year_return"] = returns["twoYearReturn"]

    return result


def extract_author_data(author: dict[str, Any]) -> dict[str, Any]:
    """
    Extract author data from nested JSON structure.

    Args:
        author: Author object from JSON

    Returns:
        Flattened dict with author data fields
    """
    if not author:
        return {}

    result: dict[str, Any] = {}

    if author.get("authorName"):
        result["author_name"] = author["authorName"]

    if author.get("id"):
        result["author_id"] = author["id"]

    if author.get("authorBio"):
        result["author_bio"] = author["authorBio"]

    if author.get("twitter"):
        result["twitter"] = author["twitter"]

    if author.get("baseUrl"):
        result["base_url"] = author["baseUrl"]

    if author.get("isProfessional") is not None:
        result["is_professional"] = author["isProfessional"]

    if author.get("isTopAuthor") is not None:
        result["is_top_author"] = author["isTopAuthor"]

    # Author returns (nested)
    author_returns = author.get("authorReturns")
    if author_returns:
        if author_returns.get("oneMonthReturn") is not None:
            result["author_1m_return"] = author_returns["oneMonthReturn"]

        if author_returns.get("threeMonthReturn") is not None:
            result["author_3m_return"] = author_returns["threeMonthReturn"]

        if author_returns.get("oneYearReturn") is not None:
            result["author_1y_return"] = author_returns["oneYearReturn"]

    return result


def parse_raw_pitch(raw_data: dict[str, Any], feed_type: str) -> Pitch:
    """
    Parse raw JSON pitch data into a Pitch model.

    Args:
        raw_data: Raw JSON dict from Yellowbrick API/embedded data
        feed_type: Feed type ('big_money' or 'elite')

    Returns:
        Immutable Pitch model instance

    Raises:
        ValueError: If required fields are missing
    """
    # Extract ticker (required)
    ticker = raw_data.get("givenTicker")
    if not ticker:
        ticker = "UNKNOWN"

    # Extract pitch ID (required)
    pitch_id = str(raw_data.get("id", ""))
    if not pitch_id:
        raise ValueError("pitch_id is required")

    # Extract nested objects (handle None gracefully)
    author_obj = raw_data.get("author") or {}
    company_obj = raw_data.get("company") or {}
    returns_obj = raw_data.get("returns") or {}

    # Extract author name
    author_name = author_obj.get("authorName", "Unknown") or "Unknown"

    # Determine author type
    author_type = determine_author_type(author_obj)

    # Determine pitch type from sentiment
    pitch_type = determine_pitch_type(raw_data.get("sentiment"))

    # Extract target price
    target_price = None
    if raw_data.get("priceTarget") is not None:
        target_price = Decimal(str(raw_data["priceTarget"]))

    # Build metadata dict with all additional fields
    metadata: dict[str, Any] = {}

    # Company data
    company_data = extract_company_data(company_obj)
    metadata.update(company_data)

    # Returns data
    returns_data = extract_returns_data(returns_obj)
    metadata.update(returns_data)

    # Author metadata
    author_data = extract_author_data(author_obj)
    if author_data.get("twitter"):
        metadata["author_twitter"] = author_data["twitter"]
    if author_data.get("base_url"):
        metadata["author_url"] = author_data["base_url"]
    if author_data.get("is_top_author") is not None:
        metadata["is_top_author"] = author_data["is_top_author"]
    if author_data.get("author_bio"):
        metadata["author_bio"] = author_data["author_bio"]

    # Content metadata
    if raw_data.get("wordCount") is not None:
        metadata["word_count"] = raw_data["wordCount"]
    if raw_data.get("readTime") is not None:
        metadata["read_time"] = raw_data["readTime"]
    if raw_data.get("category"):
        metadata["category"] = raw_data["category"]
    if raw_data.get("givenUpsidePct") is not None:
        metadata["upside_pct"] = raw_data["givenUpsidePct"]
    if raw_data.get("currentUpside") is not None:
        metadata["current_upside"] = raw_data["currentUpside"]
    if raw_data.get("isAnonymous") is not None:
        metadata["is_anonymous"] = raw_data["isAnonymous"]
    if raw_data.get("isHidden") is not None:
        metadata["is_hidden"] = raw_data["isHidden"]

    # Create and return Pitch model
    return Pitch(
        ticker=ticker,
        feed_type=feed_type,
        pitch_id=pitch_id,
        author=author_name,
        author_type=author_type,
        pitch_date=raw_data.get("dateOriginal"),
        pitch_type=pitch_type,
        title=raw_data.get("title"),
        summary=raw_data.get("oneLinerText"),
        full_content=raw_data.get("condensedText"),
        target_price=target_price,
        source_url=raw_data.get("url"),
        filing_type=raw_data.get("source"),
        metadata=metadata if metadata else None,
    )


def parse_pitches_list(
    raw_pitches: list[dict[str, Any]],
    feed_type: str,
) -> list[Pitch]:
    """
    Parse a list of raw JSON pitches into Pitch models.

    Invalid entries are skipped (logged but not raised).
    Original list is never modified.

    Args:
        raw_pitches: List of raw JSON dicts
        feed_type: Feed type ('big_money' or 'elite')

    Returns:
        New list of successfully parsed Pitch models
    """
    result: list[Pitch] = []

    for raw_pitch in raw_pitches:
        try:
            pitch = parse_raw_pitch(raw_pitch, feed_type)
            result.append(pitch)
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Skipping invalid pitch entry: %s", e)
            continue

    return result
