# FMP Data Client

A Python library for retrieving and analyzing financial data from [Financial Modeling Prep (FMP) API](https://site.financialmodelingprep.com/developer/docs), designed for integration with an AI-powered trading orchestrator.

## 📚 Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- **[DOCKER.md](DOCKER.md)** - Docker deployment guide
- **[REST_API.md](REST_API.md)** - REST API reference
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

## Overview

This library provides a comprehensive, tier-aware interface to FMP's financial data APIs with:

- **Selective data retrieval**: Request only what you need (quote, fundamentals, transcripts, etc.)
- **Concurrent API calls**: Async operations to fetch multiple data types simultaneously
- **Intelligent caching**: MySQL-backed persistent storage for immutable data (historical financials, SEC filings)
- **LLM pre-summarization**: Automatic summarization of verbose content (earnings transcripts, SEC filings) to optimize orchestrator token usage
- **Tier-aware access**: Automatic enforcement of API tier limitations (Starter → Premium → Ultimate)
- **Structured output**: Consistent Pydantic models for all data types

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                           │
│              (requests specific data for ticker)                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FMPDataClient                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ DataFetcher │  │ CacheLayer  │  │ LLMSummarizer           │  │
│  │  (async)    │  │  (MySQL)    │  │ (Haiku/Sonnet/Opus)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FMP API (financialmodelingprep.com)          │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install fmp-data-client
# Or for development
pip install -e ".[dev]"
```

### Dependencies

```
aiohttp>=3.9.0
pydantic>=2.0.0
mysql-connector-python>=8.0.0
anthropic>=0.18.0  # For LLM summarization
tenacity>=8.2.0    # Retry logic
python-dateutil>=2.8.0
```

## Configuration

```python
from fmp_data_client import FMPDataClient, FMPConfig, Tier

config = FMPConfig(
    api_key="your_fmp_api_key",
    tier=Tier.STARTER,  # STARTER, PREMIUM, or ULTIMATE
    
    # MySQL cache configuration
    cache_enabled=True,
    mysql_host="localhost",
    mysql_port=3306,
    mysql_user="fmp_cache",
    mysql_password="your_password",
    mysql_database="fmp_data",
    
    # LLM summarization configuration
    summarization_enabled=True,
    anthropic_api_key="your_anthropic_key",
    default_summary_model="claude-3-haiku-20240307",  # Cost-effective default
    transcript_summary_model="claude-3-5-sonnet-20241022",  # Better for nuanced analysis
    
    # Rate limiting
    calls_per_minute=300,  # Starter tier limit
    max_concurrent_requests=10,
)

client = FMPDataClient(config)
```

### Environment Variables

**For Local Python Usage**:

```bash
FMP_API_KEY=your_fmp_api_key
FMP_TIER=STARTER  # STARTER, PREMIUM, ULTIMATE

# Cache
FMP_CACHE_ENABLED=true
FMP_MYSQL_HOST=localhost
FMP_MYSQL_PORT=3306
FMP_MYSQL_USER=fmp_cache
FMP_MYSQL_PASSWORD=your_password
FMP_MYSQL_DATABASE=fmp_data

# LLM Summarization
FMP_SUMMARIZATION_ENABLED=false
ANTHROPIC_API_KEY=your_anthropic_key
```

**For Docker Deployment**: See [DOCKER.md](DOCKER.md) - uses different variable names (`MYSQL_*` instead of `FMP_MYSQL_*`).

## Usage

### Basic Usage - Selective Data Retrieval

```python
import asyncio
from fmp_data_client import FMPDataClient, DataRequest

async def main():
    client = FMPDataClient.from_env()
    
    # Request only specific data types
    request = DataRequest(
        symbol="AAPL",
        include_quote=True,           # Current price, volume, change
        include_profile=True,         # Company overview
        include_fundamentals=False,   # Skip balance sheet, income statement
        include_transcripts=False,    # Skip earnings calls
    )
    
    data = await client.get_ticker_data(request)
    print(f"Current price: ${data.quote.price}")
    print(f"Market cap: ${data.profile.market_cap:,.0f}")

asyncio.run(main())
```

### Full Analysis Request

```python
async def full_analysis():
    client = FMPDataClient.from_env()
    
    request = DataRequest(
        symbol="AAPL",
        
        # Real-time data
        include_quote=True,
        include_aftermarket=True,
        
        # Company info
        include_profile=True,
        include_peers=True,
        include_executives=True,
        
        # Fundamentals
        include_fundamentals=True,    # Income, Balance, Cash Flow
        fundamentals_periods=5,       # Last 5 periods (quarters or years)
        fundamentals_period_type="quarter",
        include_key_metrics=True,
        include_ratios=True,
        include_financial_scores=True,
        
        # Valuation
        include_dcf=True,
        include_enterprise_value=True,
        
        # Historical data
        include_historical_prices=True,
        historical_days=365,          # 1 year of daily prices
        
        # Analyst data
        include_analyst_estimates=True,
        include_price_targets=True,
        include_grades=True,
        
        # Events
        include_dividends=True,
        include_splits=True,
        include_earnings_calendar=True,
        
        # Ownership (requires ULTIMATE tier)
        include_institutional_holdings=True,
        include_insider_trades=True,
        
        # Transcripts (requires ULTIMATE tier)
        include_transcripts=True,
        transcript_count=4,           # Last 4 earnings calls
        summarize_transcripts=True,   # Pre-summarize with LLM
        
        # SEC filings
        include_sec_filings=True,
        sec_filing_types=["10-K", "10-Q", "8-K"],
        sec_filing_count=10,
        summarize_filings=True,       # Pre-summarize with LLM
        
        # News
        include_news=True,
        news_count=20,
    )
    
    data = await client.get_ticker_data(request)
    return data
```

### Concurrent Multi-Ticker Requests

```python
async def analyze_portfolio(symbols: list[str]):
    client = FMPDataClient.from_env()
    
    # Create requests for multiple tickers
    requests = [
        DataRequest(
            symbol=symbol,
            include_quote=True,
            include_profile=True,
            include_key_metrics=True,
        )
        for symbol in symbols
    ]
    
    # Fetch all concurrently (respects rate limits)
    results = await client.get_multiple_tickers(requests)
    
    return {r.symbol: r for r in results}

# Usage
portfolio = await analyze_portfolio(["AAPL", "MSFT", "GOOGL", "AMZN", "META"])
```

### Quick Quote Check (Minimal API Usage)

```python
async def check_price(symbol: str):
    """Minimal request for just current price."""
    client = FMPDataClient.from_env()
    
    quote = await client.get_quote(symbol)
    return {
        "symbol": quote.symbol,
        "price": quote.price,
        "change_percent": quote.change_percent,
        "volume": quote.volume,
    }
```

## API Tier Awareness

The library automatically handles tier limitations:

### Starter Tier ($22/mo) - 300 calls/min
- ✅ Company profile & search
- ✅ Stock quotes (real-time)
- ✅ Historical prices (5 years, EOD only)
- ✅ Annual fundamentals (Income, Balance Sheet, Cash Flow)
- ✅ Key metrics & ratios
- ✅ Dividends & splits
- ✅ Stock news
- ✅ Crypto & Forex
- ❌ Earnings transcripts
- ❌ Institutional holdings (13F)
- ❌ Intraday charts
- ❌ Technical indicators (limited)

### Premium Tier ($59/mo) - 750 calls/min
- Everything in Starter, plus:
- ✅ 30+ years historical data
- ✅ UK & Canada coverage
- ✅ Full fundamentals (quarterly)
- ✅ Intraday charts (5min, 15min, 30min, 1hr)
- ✅ Technical indicators
- ✅ Corporate calendars
- ❌ Earnings transcripts
- ❌ Institutional holdings (13F)
- ❌ 1-minute intraday
- ❌ Bulk endpoints

### Ultimate Tier ($149/mo) - 3000 calls/min
- Everything in Premium, plus:
- ✅ Global coverage
- ✅ Earnings call transcripts
- ✅ ETF & Mutual Fund holdings
- ✅ 13F Institutional holdings
- ✅ 1-minute intraday
- ✅ Bulk & batch endpoints

```python
# The client will warn or skip unavailable endpoints
request = DataRequest(
    symbol="AAPL",
    include_transcripts=True,  # Requires ULTIMATE
    include_institutional_holdings=True,  # Requires ULTIMATE
)

data = await client.get_ticker_data(request)
# On STARTER tier: data.transcripts will be None with a warning logged
```

## Data Models

All responses use Pydantic models for type safety and consistency:

```python
from fmp_data_client.models import (
    TickerData,
    Quote,
    CompanyProfile,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    KeyMetrics,
    FinancialRatios,
    EarningsTranscript,
    TranscriptSummary,
    InstitutionalHolder,
    InsiderTrade,
    SECFiling,
    FilingSummary,
    PriceTarget,
    AnalystGrade,
    DividendRecord,
    StockSplit,
    HistoricalPrice,
    NewsArticle,
)

# Example: TickerData structure
class TickerData(BaseModel):
    symbol: str
    retrieved_at: datetime
    
    # Real-time
    quote: Quote | None
    aftermarket_quote: Quote | None
    
    # Company info
    profile: CompanyProfile | None
    peers: list[str] | None
    executives: list[Executive] | None
    
    # Fundamentals
    income_statements: list[IncomeStatement] | None
    balance_sheets: list[BalanceSheet] | None
    cash_flow_statements: list[CashFlowStatement] | None
    key_metrics: list[KeyMetrics] | None
    ratios: list[FinancialRatios] | None
    financial_scores: FinancialScores | None
    
    # Valuation
    dcf_valuation: DCFValuation | None
    enterprise_value: EnterpriseValue | None
    
    # Historical
    historical_prices: list[HistoricalPrice] | None
    
    # Analyst
    analyst_estimates: list[AnalystEstimate] | None
    price_targets: PriceTargetSummary | None
    grades: list[AnalystGrade] | None
    
    # Events
    dividends: list[DividendRecord] | None
    splits: list[StockSplit] | None
    earnings_calendar: list[EarningsEvent] | None
    
    # Ownership
    institutional_holders: list[InstitutionalHolder] | None
    insider_trades: list[InsiderTrade] | None
    
    # Transcripts & Filings
    transcripts: list[EarningsTranscript] | None
    transcript_summaries: list[TranscriptSummary] | None
    sec_filings: list[SECFiling] | None
    filing_summaries: list[FilingSummary] | None
    
    # News
    news: list[NewsArticle] | None
```

## Caching Strategy

### What Gets Cached (MySQL)

The following data is cached permanently or with long TTLs since it rarely/never changes:

```python
# Permanent cache (immutable historical data)
PERMANENT_CACHE = [
    "income_statements",      # Historical financials don't change
    "balance_sheets",
    "cash_flow_statements", 
    "historical_prices",      # Past prices are immutable
    "dividends",              # Historical dividends
    "splits",                 # Historical splits
    "sec_filings",            # Filed documents don't change
    "transcripts",            # Published transcripts don't change
    "transcript_summaries",   # Our generated summaries
    "filing_summaries",
]

# Long TTL cache (24 hours)
LONG_CACHE = [
    "profile",                # Company info changes rarely
    "key_metrics",            # Updated quarterly
    "ratios",
    "financial_scores",
    "dcf_valuation",
    "peers",
    "executives",
]

# Short TTL cache (1 hour)
SHORT_CACHE = [
    "analyst_estimates",
    "price_targets",
    "grades",
    "institutional_holders",  # Updated quarterly (13F)
    "news",
]

# No cache (always fetch fresh)
NO_CACHE = [
    "quote",                  # Real-time price
    "aftermarket_quote",
]
```

### Cache Schema

```sql
-- Main ticker data cache
CREATE TABLE ticker_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    period_key VARCHAR(50),  -- e.g., "2024-Q1" for quarterly data
    data JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    
    UNIQUE KEY idx_symbol_type_period (symbol, data_type, period_key),
    INDEX idx_expires (expires_at)
);

-- Transcript summaries (separate for quick lookup)
CREATE TABLE transcript_summaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    summary_model VARCHAR(100) NOT NULL,
    key_points JSON NOT NULL,
    sentiment VARCHAR(20),
    guidance_summary TEXT,
    notable_quotes JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY idx_transcript (symbol, fiscal_year, fiscal_quarter, summary_model)
);

-- Filing summaries
CREATE TABLE filing_summaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    filing_type VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,
    accession_number VARCHAR(50) NOT NULL,
    summary_model VARCHAR(100) NOT NULL,
    summary JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY idx_filing (symbol, accession_number, summary_model)
);
```

### Cache Usage

```python
# Force refresh (bypass cache)
data = await client.get_ticker_data(request, force_refresh=True)

# Check cache status
cache_info = await client.get_cache_info("AAPL")
print(f"Cached data types: {cache_info.cached_types}")
print(f"Cache size: {cache_info.total_size_mb:.2f} MB")

# Clear cache for a symbol
await client.clear_cache("AAPL")

# Clear all cache
await client.clear_all_cache()
```

## LLM Summarization

### Earnings Transcript Summarization

```python
# Automatic summarization when fetching
request = DataRequest(
    symbol="AAPL",
    include_transcripts=True,
    transcript_count=4,
    summarize_transcripts=True,
)

data = await client.get_ticker_data(request)

# Access summaries
for summary in data.transcript_summaries:
    print(f"\n=== Q{summary.quarter} {summary.year} ===")
    print(f"Sentiment: {summary.sentiment}")
    print(f"Key Points:")
    for point in summary.key_points:
        print(f"  • {point}")
    print(f"Guidance: {summary.guidance_summary}")
```

### Summary Model Structure

```python
class TranscriptSummary(BaseModel):
    symbol: str
    fiscal_year: int
    fiscal_quarter: int
    
    # Overall assessment
    sentiment: Literal["bullish", "cautiously_optimistic", "neutral", "cautious", "bearish"]
    confidence_score: float  # 0-1, how confident the LLM is in its assessment
    
    # Key points (5-10 bullet points)
    key_points: list[str]
    
    # Financial highlights
    revenue_commentary: str | None
    margin_commentary: str | None
    guidance_summary: str | None
    guidance_changes: list[str] | None  # Changes from prior guidance
    
    # Strategic highlights
    strategic_initiatives: list[str] | None
    risks_mentioned: list[str] | None
    opportunities_mentioned: list[str] | None
    
    # Notable quotes (verbatim from executives)
    notable_quotes: list[dict[str, str]] | None  # {"speaker": "Tim Cook", "quote": "..."}
    
    # Q&A highlights
    analyst_concerns: list[str] | None  # Key concerns raised by analysts
    management_responses: list[str] | None  # How management addressed concerns
    
    # Metadata
    model_used: str
    summarized_at: datetime
    word_count_original: int
    token_count_summary: int
```

### SEC Filing Summarization

```python
class FilingSummary(BaseModel):
    symbol: str
    filing_type: str  # "10-K", "10-Q", "8-K"
    filing_date: date
    accession_number: str
    
    # Overview
    summary: str  # 2-3 paragraph overview
    
    # Key sections (varies by filing type)
    business_overview: str | None  # 10-K
    risk_factors: list[str] | None  # Key risks identified
    financial_highlights: dict[str, Any] | None
    material_events: list[str] | None  # 8-K specific
    
    # Changes from prior filing
    notable_changes: list[str] | None
    
    # Metadata
    model_used: str
    summarized_at: datetime
```

## Institutional Holdings Analysis

### Weighted Holder Scoring

The library includes a holder weighting system to differentiate passive vs. active funds:

```python
from fmp_data_client.analysis import InstitutionalAnalyzer

analyzer = InstitutionalAnalyzer()

# Get weighted institutional analysis
analysis = await analyzer.analyze_holdings(
    symbol="AAPL",
    holders=data.institutional_holders,
)

print(f"Total institutional ownership: {analysis.total_ownership_pct:.1f}%")
print(f"Active fund ownership: {analysis.active_ownership_pct:.1f}%")
print(f"Passive fund ownership: {analysis.passive_ownership_pct:.1f}%")
print(f"\nSignificant active fund moves:")
for move in analysis.significant_active_moves:
    print(f"  {move.holder_name}: {move.change_description}")
```

### Holder Classification

```python
class HolderClassification(BaseModel):
    """Classification of institutional holder type and quality."""
    
    cik: str
    name: str
    
    # Classification
    holder_type: Literal[
        "passive_index",       # Vanguard, BlackRock index funds
        "passive_etf",         # ETF providers
        "active_quantitative", # Renaissance, Two Sigma
        "active_fundamental",  # Berkshire, value funds
        "active_growth",       # ARK, growth-focused
        "hedge_fund",          # Hedge funds
        "pension",             # Pension funds
        "sovereign",           # Sovereign wealth funds
        "other",
    ]
    
    # Quality signals (for active managers)
    historical_alpha: float | None      # Estimated alpha vs benchmark
    track_record_years: int | None
    reputation_score: float | None      # 0-1, based on known performance
    
    # Weighting for signals
    signal_weight: float  # 0-1, how much weight to give their moves
    # - Passive funds: 0.0-0.1 (their moves are mechanical)
    # - Average active: 0.3-0.5
    # - High-quality active: 0.7-1.0

# Pre-configured classifications for known institutions
KNOWN_HOLDERS = {
    "0001067983": HolderClassification(
        cik="0001067983",
        name="Berkshire Hathaway",
        holder_type="active_fundamental",
        historical_alpha=0.03,  # ~3% annual alpha
        track_record_years=50,
        reputation_score=0.95,
        signal_weight=0.9,
    ),
    "0000102909": HolderClassification(
        cik="0000102909",
        name="Vanguard Group",
        holder_type="passive_index",
        signal_weight=0.05,  # Mostly mechanical, low signal
    ),
    # ... more pre-configured holders
}
```

## Rate Limiting

```python
# Automatic rate limiting based on tier
client = FMPDataClient(config)  # Uses config.calls_per_minute

# Manual rate limit adjustment
client.set_rate_limit(calls_per_minute=200)  # Be conservative

# Rate limit status
status = client.get_rate_limit_status()
print(f"Calls remaining this minute: {status.remaining}")
print(f"Reset in: {status.reset_in_seconds}s")
```

### Retry Logic

```python
# Built-in retry with exponential backoff
# Configurable in FMPConfig
config = FMPConfig(
    # ...
    max_retries=3,
    retry_base_delay=1.0,  # seconds
    retry_max_delay=30.0,  # seconds
    retry_on_status_codes=[429, 500, 502, 503, 504],
)
```

## CLI Tool

```bash
# Quick quote
fmp quote AAPL

# Full analysis (JSON output)
fmp analyze AAPL --output json

# Specific data
fmp fundamentals AAPL --periods 4 --type quarter

# Multiple tickers
fmp quotes AAPL MSFT GOOGL

# Cache management
fmp cache status
fmp cache clear AAPL
fmp cache clear --all
```

## Docker Deployment

**See [DOCKER.md](DOCKER.md) for complete deployment guide.**

Quick start:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your API keys
nano .env

# 3. Start services
docker compose up -d

# 4. Check health
curl http://localhost:8000/health
```

The deployment includes:
- REST API server (FastAPI/Uvicorn)
- MySQL database for caching
- Automatic health checks
- Persistent storage volumes

See [REST_API.md](REST_API.md) for API documentation.

## API Reference

### FMPDataClient Methods

| Method | Description |
|--------|-------------|
| `get_ticker_data(request)` | Fetch data based on DataRequest |
| `get_multiple_tickers(requests)` | Concurrent fetch for multiple tickers |
| `get_quote(symbol)` | Quick quote fetch |
| `get_batch_quotes(symbols)` | Batch quote fetch |
| `get_profile(symbol)` | Company profile |
| `get_fundamentals(symbol, periods, period_type)` | Financial statements |
| `get_historical_prices(symbol, days)` | Historical price data |
| `get_transcript(symbol, year, quarter)` | Single earnings transcript |
| `get_transcripts(symbol, count)` | Multiple transcripts |
| `get_sec_filings(symbol, types, count)` | SEC filings |
| `get_institutional_holders(symbol)` | 13F institutional holdings |
| `get_insider_trades(symbol, days)` | Insider trading activity |
| `summarize_transcript(transcript)` | LLM summarization |
| `summarize_filing(filing)` | LLM summarization |

### DataRequest Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `symbol` | str | required | Ticker symbol |
| `include_quote` | bool | False | Current price data |
| `include_aftermarket` | bool | False | After-hours quote |
| `include_profile` | bool | False | Company profile |
| `include_peers` | bool | False | Peer companies |
| `include_executives` | bool | False | Key executives |
| `include_fundamentals` | bool | False | Financial statements |
| `fundamentals_periods` | int | 4 | Number of periods |
| `fundamentals_period_type` | str | "quarter" | "quarter" or "annual" |
| `include_key_metrics` | bool | False | Key financial metrics |
| `include_ratios` | bool | False | Financial ratios |
| `include_financial_scores` | bool | False | Piotroski, Altman Z |
| `include_dcf` | bool | False | DCF valuation |
| `include_enterprise_value` | bool | False | Enterprise value |
| `include_historical_prices` | bool | False | Price history |
| `historical_days` | int | 365 | Days of history |
| `include_analyst_estimates` | bool | False | Analyst estimates |
| `include_price_targets` | bool | False | Price targets |
| `include_grades` | bool | False | Analyst grades |
| `include_dividends` | bool | False | Dividend history |
| `include_splits` | bool | False | Stock splits |
| `include_earnings_calendar` | bool | False | Upcoming earnings |
| `include_institutional_holdings` | bool | False | 13F data (ULTIMATE) |
| `include_insider_trades` | bool | False | Insider transactions |
| `include_transcripts` | bool | False | Earnings calls (ULTIMATE) |
| `transcript_count` | int | 4 | Number of transcripts |
| `summarize_transcripts` | bool | False | LLM summarization |
| `include_sec_filings` | bool | False | SEC filings |
| `sec_filing_types` | list | ["10-K","10-Q","8-K"] | Filing types |
| `sec_filing_count` | int | 10 | Number of filings |
| `summarize_filings` | bool | False | LLM summarization |
| `include_news` | bool | False | Recent news |
| `news_count` | int | 20 | Number of articles |

## Project Structure

```
fmp-data-client/
├── fmp_data_client/
│   ├── __init__.py
│   ├── client.py              # Main FMPDataClient class
│   ├── config.py              # Configuration handling
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py            # Base models
│   │   ├── quote.py           # Quote models
│   │   ├── profile.py         # Company profile models
│   │   ├── fundamentals.py    # Financial statement models
│   │   ├── valuation.py       # DCF, enterprise value
│   │   ├── analyst.py         # Estimates, grades, targets
│   │   ├── ownership.py       # Institutional, insider
│   │   ├── transcripts.py     # Earnings transcripts
│   │   ├── filings.py         # SEC filings
│   │   ├── events.py          # Dividends, splits, calendar
│   │   ├── news.py            # News articles
│   │   └── request.py         # DataRequest model
│   ├── fetcher/
│   │   ├── __init__.py
│   │   ├── base.py            # Base async fetcher
│   │   ├── endpoints.py       # FMP endpoint definitions
│   │   └── tier.py            # Tier-aware endpoint access
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── mysql.py           # MySQL cache implementation
│   │   └── ttl.py             # TTL management
│   ├── summarizer/
│   │   ├── __init__.py
│   │   ├── base.py            # Base summarizer
│   │   ├── transcripts.py     # Transcript summarization
│   │   └── filings.py         # Filing summarization
│   ├── analysis/
│   │   ├── __init__.py
│   │   └── institutional.py   # Institutional holder analysis
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py            # CLI implementation
│   └── server/
│       ├── __init__.py
│       └── api.py             # Optional REST API server
├── tests/
│   ├── test_client.py
│   ├── test_cache.py
│   ├── test_summarizer.py
│   └── fixtures/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=fmp_data_client

# Specific test file
pytest tests/test_client.py -v
```

## Acknowledgments

- [Financial Modeling Prep](https://financialmodelingprep.com/) for the API
- [Anthropic](https://anthropic.com/) for Claude LLM capabilities
