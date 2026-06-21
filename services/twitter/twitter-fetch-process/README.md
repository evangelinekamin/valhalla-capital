# Twitter Monitoring System

Automated Twitter monitoring for financial analysis and trading signals. Uses self-hosted Nitter for RSS ingestion, Miniflux for feed aggregation, Claude-powered LLM triage for classification, and a REST API for downstream consumption.

## Architecture

```
Twitter/X
    |
    v
Nitter (port 8080)        Self-hosted Twitter -> RSS proxy
    |
    v
Miniflux (port 8081)      RSS feed aggregator with API
    |
    v
Scraper (port 8082)       Single-process Python service:
  |-- Pre-Filter           Rule-based skip/accept/triage routing (~80% skip rate)
  |-- Claude Haiku         LLM classification for remaining tweets
  |-- Ticker Extractor     Stock symbol extraction (LLM + regex)
  |-- Sentiment Analyzer   Bullish/bearish/neutral classification
  |-- PostgreSQL Storage   Structured data for trading system
  |-- REST API             FastAPI endpoints for querying results
```

### Network Layout

Deployed on the **data-collection LXC** (<LAN_IP>) alongside other data acquisition services.

| LXC | IP | Role |
|-----|-----|------|
| data-collection | <LAN_IP> | This service + other data scrapers |
| fmp | <LAN_IP> | Financial Modeling Prep connector |
| trading | <LAN_IP> | Trading execution (IB API) |
| overseer | <LAN_IP> | Orchestration / Claude overseer |
| dashboard | <LAN_IP> | Monitoring dashboard |

The scraper API (port 8082) is accessible from all LXCs. Nitter and Miniflux are bound to localhost only.

## Prerequisites

- Docker and Docker Compose
- ~2GB RAM for all services
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com/))

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env

# Optional: override if running scraper from host instead of Docker
# export MINIFLUX_URL=http://localhost:8081

# Generate secure passwords
sed -i "s/^MINIFLUX_DB_PASSWORD=$/MINIFLUX_DB_PASSWORD=$(openssl rand -hex 32)/" .env
sed -i "s/^MINIFLUX_ADMIN_PASSWORD=$/MINIFLUX_ADMIN_PASSWORD=$(openssl rand -hex 16)/" .env
sed -i "s/^PROCESSING_DB_PASSWORD=$/PROCESSING_DB_PASSWORD=$(openssl rand -hex 32)/" .env

# Add your Anthropic API key
nano .env
```

### 2. Start Infrastructure (Without Scraper)

```bash
docker compose up -d nitter miniflux processing-db
docker compose ps  # wait for all services to be healthy
```

### 3. Get Miniflux API Key

1. Open http://localhost:8081
2. Login with credentials from `.env`
3. Go to Settings -> API Keys -> Create new key
4. Add to `.env`: `MINIFLUX_API_KEY=your-key-here`

### 4. Add Twitter Feeds

```bash
# Create accounts list
cat > scraper/accounts.txt << 'EOF'
BillAckman
elonmusk
chamath
karpathy
unusual_whales
EOF

# Add feeds to Miniflux (from host)
pip install requests
export MINIFLUX_URL=http://localhost:8081
export MINIFLUX_API_KEY=your-key-here
python scripts/add_twitter_feeds.py scraper/accounts.txt --shuffle --min-delay 10 --max-delay 30
```

### 5. Start Scraper

```bash
docker compose up -d scraper
docker compose logs -f scraper
```

## Pre-Deployment Checklist (Debian LXC)

Run these checks before moving to live testing:

1. **Validate Python test suite**
   ```bash
   cd scraper && pytest -q
   ```
2. **Validate shell scripts syntax**
   ```bash
   bash -n backup.sh
   ```
3. **Confirm Docker service health**
   ```bash
   docker compose up -d
   docker compose ps
   curl http://localhost:8082/health
   ```
4. **Verify backup pipeline**
   ```bash
   ./backup.sh
   ls -lh backups/
   ```

For your multi-LXC setup, keep only port `8082` externally reachable and leave Nitter/Miniflux bound to localhost as already configured.

## API Reference

The scraper exposes a REST API on port 8082.

### GET /health

Returns system health including database connectivity and processing thread status.

```bash
curl http://<LAN_IP>:8082/health
```

### GET /tweets

Query classified tweets with filters.

```bash
# Critical tweets
curl "http://<LAN_IP>:8082/tweets?classification=CRITICAL&limit=10"

# Bullish tweets for a ticker
curl "http://<LAN_IP>:8082/tweets?ticker=AAPL&sentiment=bullish"

# By username with confidence threshold
curl "http://<LAN_IP>:8082/tweets?username=elonmusk&min_confidence=0.8"
```

**Parameters**: `classification`, `username`, `sentiment`, `ticker`, `min_confidence`, `limit` (1-100), `offset`

### GET /tweets/{id}

Get a specific tweet by database ID.

### GET /stats

Aggregated statistics: classification breakdown, sentiment distribution, pre-filter effectiveness, top tickers, top users.

```bash
curl http://<LAN_IP>:8082/stats
```

## Configuration

### Account Classification (`scraper/config/account_config.json`)

Route accounts to different processing pipelines:

- **high_signal**: Bypass LLM, mark as IMPORTANT (e.g., BillAckman, elonmusk)
- **noisy**: Apply aggressive filtering
- **tickers_only**: Extract tickers only, skip classification

### Pre-Filter Rules (`scraper/config/filter_config.json`)

Rule-based filtering to reduce LLM costs (~80% skip rate):

- Skip patterns: retweets, spam, promotional, crypto spam, memes
- Text quality: minimum length/words, max emojis/hashtags/URLs
- URL blocklist

### LLM Triage (`scraper/config/triage_config.json`)

- **Model**: Claude 3.5 Haiku (cost-optimized for classification)
- **Batch size**: 15 tweets per API call
- **Classifications**: CRITICAL, IMPORTANT, ROUTINE, SKIP
- **Fallback**: ROUTINE on any error

## Database Schema

```sql
CREATE TABLE tweets (
    id SERIAL PRIMARY KEY,
    miniflux_id INTEGER UNIQUE NOT NULL,
    feed_id INTEGER,
    tweet_id TEXT,
    username TEXT,
    title TEXT,
    content TEXT,
    url TEXT,
    published_at TIMESTAMP,
    pre_filter_action TEXT,    -- 'skip', 'accept', 'triage'
    pre_filter_reason TEXT,
    classification TEXT,       -- 'CRITICAL', 'IMPORTANT', 'ROUTINE', 'SKIP'
    confidence FLOAT,
    tickers TEXT[],            -- PostgreSQL array: ['AAPL', 'MSFT']
    sentiment TEXT,            -- 'bullish', 'bearish', 'neutral'
    fetched_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP
);
```

### Direct Database Access

```bash
docker exec -it processing-db psql -U postgres -d twitter_data

# Recent critical tweets
SELECT username, title, tickers, sentiment, published_at
FROM tweets
WHERE classification = 'CRITICAL'
ORDER BY published_at DESC LIMIT 10;

# Classification breakdown
SELECT classification, COUNT(*) FROM tweets GROUP BY classification;

# Top mentioned tickers
SELECT unnest(tickers) as ticker, COUNT(*) as mentions
FROM tweets WHERE tickers IS NOT NULL
GROUP BY ticker ORDER BY mentions DESC LIMIT 20;
```

## Operations

### Monitoring

```bash
docker compose ps                           # Service status
docker compose logs -f scraper              # Live logs
curl http://localhost:8082/health            # Health check
curl http://localhost:8082/stats             # Statistics
docker compose logs scraper | grep "cost"   # LLM costs
```

### Backups

```bash
./backup.sh                                 # Manual backup

# Automated (add to crontab):
# 0 2 * * * /path/to/twitter-fetch-process/backup.sh
```

Backups are stored in `./backups/` with 7-day retention.

### Restart / Update

```bash
docker compose restart scraper              # Restart scraper
docker compose build scraper && docker compose up -d scraper  # Rebuild
docker compose pull && docker compose up -d  # Update all images
```

## Cost Estimates

With pre-filtering enabled (Claude 3.5 Haiku):

| Metric | Value |
|--------|-------|
| Input tweets/day | ~10,000 |
| After pre-filter | ~2,000 (80% skipped) |
| Daily LLM cost | ~$0.32 |
| Monthly LLM cost | ~$10 |

## Project Structure

```
twitter-fetch-process/
├── docker-compose.yml              # Service orchestration
├── .env.example                    # Environment template
├── backup.sh                       # Database backup script
├── config/nitter/nitter.conf       # Nitter configuration
├── scripts/
│   ├── add_twitter_feeds.py        # Bulk feed management
│   ├── configure_feed_intervals.py # Schedule generation
│   └── test_llm_connection.py      # API connectivity test
└── scraper/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                     # Entry point (processing + API)
    ├── api/
    │   ├── server.py               # FastAPI application
    │   ├── handlers.py             # Request handlers
    │   └── models.py               # Pydantic schemas
    ├── core/
    │   └── pipeline.py             # Processing pipeline
    ├── db/
    │   ├── connection.py           # Database connection (cached engine)
    │   └── schema.py               # SQLAlchemy ORM models
    ├── filters/
    │   ├── pre_filter.py           # Rule-based pre-filtering
    │   └── patterns.py             # Pattern detection utilities
    ├── llm/
    │   ├── client.py               # Anthropic API client
    │   ├── prompts.py              # Prompt templates
    │   ├── triage.py               # Classification engine
    │   ├── ticker_extractor.py     # Stock ticker extraction
    │   └── sentiment_analyzer.py   # Sentiment classification
    ├── config/
    │   ├── filter_config.json      # Pre-filter rules
    │   ├── account_config.json     # Account classifications
    │   └── triage_config.json      # LLM settings
    └── tests/
        ├── test_database.py        # Database tests (49 tests)
        ├── test_pre_filter.py      # Pre-filter tests (111 tests)
        └── test_triage.py          # LLM tests (mocked)
```

## Troubleshooting

**Scraper not starting**: Check `docker compose logs scraper`. Common causes:
- Missing `MINIFLUX_API_KEY` or `ANTHROPIC_API_KEY` in `.env`
- Database not ready (check `docker compose ps processing-db`)

**No tweets appearing**: Verify feeds are added in Miniflux (http://localhost:8081). Check Nitter is working: `curl http://localhost:8080/elonmusk/rss`

**High LLM costs**: Check pre-filter skip rate via `curl http://localhost:8082/stats | jq '.pre_filter_stats.skip_rate'`. Target is 80%+. Tune `filter_config.json` if lower.

**Database growing large**: Archive old tweets:
```bash
docker exec -it processing-db psql -U postgres -d twitter_data \
  -c "DELETE FROM tweets WHERE fetched_at < NOW() - INTERVAL '90 days'; VACUUM;"
```
