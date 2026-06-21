"""FMP API endpoint definitions and tier requirements."""

from enum import Enum

from ..config import Tier


class Endpoint(str, Enum):
    """FMP API endpoints (stable API)."""

    # Quote data
    QUOTE = "/stable/quote"
    AFTERMARKET_QUOTE = "/stable/aftermarket-quote"
    QUOTE_SHORT = "/stable/quote-short"

    # Company profile
    PROFILE = "/stable/profile"
    EXECUTIVES = "/stable/key-executives"

    # Corporate events
    DIVIDENDS_HISTORICAL = "/stable/dividends"
    STOCK_SPLIT_HISTORICAL = "/stable/splits"
    EARNINGS_CALENDAR = "/stable/earnings-calendar"
    EARNINGS_HISTORICAL = "/stable/earnings"

    # Fundamental statements
    INCOME_STATEMENT = "/stable/income-statement"
    BALANCE_SHEET = "/stable/balance-sheet-statement"
    CASH_FLOW = "/stable/cash-flow-statement"

    # Financial metrics
    KEY_METRICS = "/stable/key-metrics"
    FINANCIAL_RATIOS = "/stable/ratios"
    FINANCIAL_SCORES = "/stable/financial-scores"

    # Valuation
    DCF = "/stable/discounted-cash-flow"
    HISTORICAL_DCF = "/stable/levered-discounted-cash-flow"
    ENTERPRISE_VALUE = "/stable/enterprise-values"

    # Analyst data
    ANALYST_ESTIMATES = "/stable/analyst-estimates"
    PRICE_TARGET = "/stable/price-target-consensus"
    PRICE_TARGET_SUMMARY = "/stable/price-target-summary"
    PRICE_TARGET_CONSENSUS = "/stable/price-target-consensus"
    ANALYST_UPGRADES_DOWNGRADES = "/stable/grades"
    ANALYST_RECOMMENDATIONS = "/stable/grades-consensus"

    # Ownership
    INSTITUTIONAL_HOLDERS = "/stable/institutional-ownership/symbol-positions-summary"
    INSIDER_TRADING = "/stable/insider-trading/search"
    INSIDER_ROSTER = "/stable/insider-trading/statistics"

    # Historical prices
    HISTORICAL_PRICES = "/stable/historical-price-eod/full"
    HISTORICAL_PRICES_DAILY = "/stable/historical-chart/{timeframe}"

    # Earnings transcripts
    EARNING_CALL_TRANSCRIPT = "/stable/earning-call-transcript"
    BATCH_EARNING_CALL_TRANSCRIPT = "/stable/earning-call-transcript-latest"

    # SEC filings
    SEC_FILINGS = "/stable/sec-filings-search/symbol"
    SEC_RSS_FEED = "/stable/sec-filings-financials"

    # News
    STOCK_NEWS = "/stable/news/stock-latest"
    STOCK_NEWS_SENTIMENT = "/stable/news/stock"

    # Market data
    MARKET_HOURS = "/stable/all-exchange-market-hours"
    IS_MARKET_OPEN = "/stable/exchange-market-hours"

    # Symbols and search
    SYMBOL_SEARCH = "/stable/search-symbol"
    SYMBOL_LIST = "/stable/stock-list"


# Tier requirements for each endpoint
TIER_REQUIREMENTS = {
    # Free/Starter tier endpoints
    Endpoint.QUOTE: Tier.STARTER,
    Endpoint.PROFILE: Tier.STARTER,
    Endpoint.HISTORICAL_PRICES: Tier.STARTER,
    Endpoint.INCOME_STATEMENT: Tier.STARTER,
    Endpoint.BALANCE_SHEET: Tier.STARTER,
    Endpoint.CASH_FLOW: Tier.STARTER,
    Endpoint.SYMBOL_SEARCH: Tier.STARTER,
    Endpoint.SYMBOL_LIST: Tier.STARTER,
    Endpoint.STOCK_NEWS: Tier.STARTER,
    Endpoint.DCF: Tier.STARTER,
    Endpoint.KEY_METRICS: Tier.STARTER,
    Endpoint.FINANCIAL_RATIOS: Tier.STARTER,
    Endpoint.MARKET_HOURS: Tier.STARTER,
    Endpoint.IS_MARKET_OPEN: Tier.STARTER,

    # Premium tier endpoints
    Endpoint.AFTERMARKET_QUOTE: Tier.PREMIUM,
    Endpoint.EXECUTIVES: Tier.PREMIUM,
    Endpoint.DIVIDENDS_HISTORICAL: Tier.PREMIUM,
    Endpoint.STOCK_SPLIT_HISTORICAL: Tier.PREMIUM,
    Endpoint.EARNINGS_CALENDAR: Tier.PREMIUM,
    Endpoint.EARNINGS_HISTORICAL: Tier.PREMIUM,
    Endpoint.ENTERPRISE_VALUE: Tier.PREMIUM,
    Endpoint.ANALYST_ESTIMATES: Tier.PREMIUM,
    Endpoint.INSTITUTIONAL_HOLDERS: Tier.PREMIUM,
    Endpoint.INSIDER_TRADING: Tier.PREMIUM,
    Endpoint.SEC_FILINGS: Tier.PREMIUM,
    Endpoint.EARNING_CALL_TRANSCRIPT: Tier.PREMIUM,

    # Ultimate tier endpoints
    Endpoint.PRICE_TARGET: Tier.ULTIMATE,
    Endpoint.PRICE_TARGET_SUMMARY: Tier.ULTIMATE,
    Endpoint.ANALYST_UPGRADES_DOWNGRADES: Tier.ULTIMATE,
    Endpoint.ANALYST_RECOMMENDATIONS: Tier.ULTIMATE,
    Endpoint.INSIDER_ROSTER: Tier.ULTIMATE,
    Endpoint.BATCH_EARNING_CALL_TRANSCRIPT: Tier.ULTIMATE,
    Endpoint.STOCK_NEWS_SENTIMENT: Tier.ULTIMATE,
    Endpoint.SEC_RSS_FEED: Tier.ULTIMATE,
    Endpoint.FINANCIAL_SCORES: Tier.ULTIMATE,
    Endpoint.HISTORICAL_DCF: Tier.ULTIMATE,
    Endpoint.QUOTE_SHORT: Tier.ULTIMATE,
    Endpoint.HISTORICAL_PRICES_DAILY: Tier.PREMIUM,
}


# Base URL for FMP API
BASE_URL = "https://financialmodelingprep.com"


def get_endpoint_url(endpoint: Endpoint, **path_params: str) -> str:
    """Get full endpoint URL with path parameters.

    Args:
        endpoint: Endpoint enum value
        **path_params: Path parameters to format into endpoint

    Returns:
        Full endpoint path

    Example:
        >>> get_endpoint_url(Endpoint.QUOTE)
        '/stable/quote'
        >>> get_endpoint_url(Endpoint.HISTORICAL_PRICES_DAILY, timeframe="1min")
        '/stable/historical-chart/1min'
    """
    endpoint_path = endpoint.value
    if path_params:
        endpoint_path = endpoint_path.format(**path_params)
    return endpoint_path
