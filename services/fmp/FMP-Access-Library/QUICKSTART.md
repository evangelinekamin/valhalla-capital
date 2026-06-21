## FMP Data Client - Quick Start Guide

Get up and running with the FMP Data Client in minutes!

---

## 📋 Prerequisites

- Python 3.11 or higher
- FMP API key (get one at [financialmodelingprep.com](https://financialmodelingprep.com))
- Optional: MySQL for caching
- Optional: Anthropic API key for LLM summarization

---

## 🚀 Installation

### Step 1: Install the Package

```bash
# Clone the repository (or use pip when published)
cd FMP-Access-Library

# Install in development mode
pip install -e .

# Or install with all optional features
pip install -e ".[dev,cli,server]"
```

### Step 2: Set Up Environment Variables

**For Local Python Usage** (not Docker):

Create a `.env` file with these variables (no `export`):

```bash
# Required
FMP_API_KEY=your_fmp_api_key_here
FMP_TIER=STARTER  # STARTER, PREMIUM, or ULTIMATE

# Optional: MySQL Cache
FMP_CACHE_ENABLED=true
FMP_MYSQL_HOST=localhost
FMP_MYSQL_PORT=3306
FMP_MYSQL_USER=root
FMP_MYSQL_PASSWORD=your_password
FMP_MYSQL_DATABASE=fmp_cache

# Optional: LLM Summarization
FMP_SUMMARIZATION_ENABLED=true
ANTHROPIC_API_KEY=your_anthropic_key_here
```

**For Docker Deployment**: See [DOCKER.md](DOCKER.md) for the correct Docker environment setup.

### Step 3: Set Up MySQL (Optional)

If using caching:

```bash
# Create database
mysql -u root -p
CREATE DATABASE fmp_cache;

# Load schema
mysql -u root -p fmp_cache < fmp_data_client/cache/schema.sql
```

---

## 💻 Usage Examples

### Example 1: Get a Stock Quote

```python
import asyncio
from fmp_data_client import FMPDataClient

async def main():
    async with FMPDataClient.from_env() as client:
        quote = await client.get_quote("AAPL")
        print(f"AAPL: ${quote.price:.2f}")
        print(f"Change: {quote.changes_percentage:+.2f}%")
        print(f"Market Cap: {quote.market_cap_formatted}")

asyncio.run(main())
```

### Example 2: Comprehensive Stock Analysis

```python
from fmp_data_client import FMPDataClient, DataRequest

async def analyze_stock():
    async with FMPDataClient.from_env() as client:
        # Create comprehensive request
        request = DataRequest(symbol="AAPL")
        request.enable_full_analysis()

        # Fetch all data
        data = await client.get_ticker_data(request)

        # Display summary
        print(data.summary())

        # Access specific data
        if data.income_statements:
            latest = data.income_statements[0]
            print(f"Revenue: ${latest.revenue/1e9:.2f}B")
            print(f"Net Income: ${latest.net_income/1e9:.2f}B")

asyncio.run(analyze_stock())
```

### Example 3: Use LLM to Summarize Earnings Transcript

```python
from fmp_data_client import FMPDataClient, DataRequest
from fmp_data_client.summarizer import TranscriptSummarizer

async def summarize_transcript():
    async with FMPDataClient.from_env() as client:
        # Fetch transcript
        request = DataRequest(
            symbol="AAPL",
            include_transcripts=True,
            transcripts_count=1
        )
        data = await client.get_ticker_data(request)

        if data.earnings_transcripts:
            # Summarize with Claude
            summarizer = TranscriptSummarizer(client.config)
            summary = await summarizer.summarize_transcript(
                data.earnings_transcripts[0]
            )

            print("Executive Summary:")
            print(summary["executive_summary"])

            print("\nKey Metrics:")
            for metric in summary["key_metrics"]:
                print(f"  • {metric}")

            await summarizer.close()

asyncio.run(summarize_transcript())
```

---

## 🖥️ CLI Usage

The library includes a powerful command-line interface:

### Get a Quote
```bash
fmp quote AAPL
```

### Get Company Profile
```bash
fmp profile MSFT
```

### Get Financial Statements
```bash
fmp fundamentals GOOGL --periods 8
```

### Comprehensive Analysis
```bash
fmp analyze AAPL --full
```

### Get Data as JSON
```bash
fmp quote AAPL --json > aapl_quote.json
```

### Check Cache Status
```bash
fmp cache status
```

### Test API Connection
```bash
fmp config test
```

### Show Rate Limit Status
```bash
fmp rate-limit
```

---

## 📚 Common Use Cases

### Portfolio Analysis

```python
async def analyze_portfolio(symbols):
    async with FMPDataClient.from_env() as client:
        # Fetch quotes for all symbols concurrently
        quotes = await asyncio.gather(*[
            client.get_quote(symbol) for symbol in symbols
        ])

        # Calculate total value
        total_value = sum(q.market_cap for q in quotes if q.market_cap)

        for quote in quotes:
            print(f"{quote.symbol}: ${quote.price:.2f}")

symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
asyncio.run(analyze_portfolio(symbols))
```

### Fundamental Screening

```python
async def screen_stocks(symbols, min_roe=0.15):
    async with FMPDataClient.from_env() as client:
        for symbol in symbols:
            request = DataRequest(
                symbol=symbol,
                include_fundamentals=True,
                fundamentals_periods=1
            )
            data = await client.get_ticker_data(request)

            if data.key_metrics_list:
                roe = data.key_metrics_list[0].roe
                if roe >= min_roe:
                    print(f"{symbol}: ROE = {roe:.2%} ✓")

symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
asyncio.run(screen_stocks(symbols))
```

### News Monitoring

```python
async def monitor_news(symbol):
    async with FMPDataClient.from_env() as client:
        request = DataRequest(
            symbol=symbol,
            include_news=True,
            news_limit=10
        )
        data = await client.get_ticker_data(request)

        print(f"Latest news for {symbol}:")
        for article in data.news:
            print(f"- {article.title}")
            print(f"  {article.site} | {article.published_date}")

asyncio.run(monitor_news("AAPL"))
```

---

## ⚙️ Configuration Options

All configuration is done via environment variables:

### Required
- `FMP_API_KEY` - Your FMP API key
- `FMP_TIER` - Your subscription tier (starter/premium/ultimate)

### Optional - Caching
- `FMP_CACHE_ENABLED` - Enable MySQL caching (true/false)
- `FMP_MYSQL_HOST` - MySQL host (default: localhost)
- `FMP_MYSQL_PORT` - MySQL port (default: 3306)
- `FMP_MYSQL_USER` - MySQL username (default: root)
- `FMP_MYSQL_PASSWORD` - MySQL password
- `FMP_MYSQL_DATABASE` - Database name (default: fmp_cache)
- `FMP_MYSQL_POOL_SIZE` - Connection pool size (default: 5)

### Optional - LLM Summarization
- `FMP_SUMMARIZATION_ENABLED` - Enable LLM features (true/false)
- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `FMP_DEFAULT_MODEL` - Claude model (default: claude-3-haiku-20240307)

### Optional - Performance
- `FMP_MAX_CONCURRENT_REQUESTS` - Max concurrent API calls (default: 10)
- `FMP_REQUEST_TIMEOUT` - Request timeout in seconds (default: 30)
- `FMP_RETRY_ATTEMPTS` - Number of retry attempts (default: 3)
- `FMP_CALLS_PER_MINUTE` - Override default rate limit

---

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=fmp_data_client --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run with verbose output
pytest -v
```

---

## 🐛 Troubleshooting

### Error: "API key is required"
- Make sure `FMP_API_KEY` is set in your environment
- Verify the key is correct and has not expired

### Error: "This endpoint requires a higher tier subscription"
- Check your FMP tier (starter/premium/ultimate)
- Some endpoints require premium or ultimate tier
- Update `FMP_TIER` environment variable

### Error: "Rate limit exceeded"
- Wait a minute for the rate limit to reset
- Consider upgrading your FMP tier for higher limits
- Use caching to reduce API calls

### MySQL Connection Issues
- Verify MySQL is running: `systemctl status mysql`
- Check credentials in environment variables
- Ensure database exists: `mysql -e "SHOW DATABASES;"`
- Load schema: `mysql fmp_cache < fmp_data_client/cache/schema.sql`

### LLM Summarization Not Working
- Verify `FMP_SUMMARIZATION_ENABLED=true`
- Check `ANTHROPIC_API_KEY` is valid
- Ensure `anthropic` package is installed: `pip install anthropic`

---

## 📖 Next Steps

1. **Read the Full Documentation**: See `README.md` for comprehensive docs
2. **Check Examples**: Look at `examples/comprehensive_analysis.py`
3. **Review API Reference**: Explore the codebase with type hints and docstrings
4. **Join the Community**: Report issues and contribute on GitHub

---

## 🆘 Getting Help

- **Documentation**: `README.md`
- **Implementation Status**: See `CHANGELOG.md` for current status
- **Changelog**: `CHANGELOG.md`
- **Issues**: Report bugs on GitHub
- **Examples**: See `examples/` directory

---

## ⚡ Tips for Best Performance

1. **Use Caching**: Enable MySQL caching to reduce API calls
2. **Batch Requests**: Fetch multiple symbols concurrently with `asyncio.gather()`
3. **Choose the Right Model**: Use Haiku for cost-effective LLM summarization
4. **Monitor Rate Limits**: Check status with `client.get_rate_limit_status()`
5. **Reuse Client**: Use `async with` to properly manage connections

---

Happy coding! 🚀
