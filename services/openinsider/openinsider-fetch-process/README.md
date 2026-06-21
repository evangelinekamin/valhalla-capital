# OpenInsider Cluster Buys Scraper

Web scraper for tracking insider cluster buying activity from [OpenInsider.com](http://openinsider.com/latest-cluster-buys). Part of the data acquisition layer running on the `data-collection` LXC (<LAN_IP>).

## Architecture

The scraper operates in two phases:

**Phase 1 -- Cluster Buys**: Scrapes the main cluster buys table capturing aggregated data (ticker, company, insider count, prices, volumes, performance metrics). Runs every 6 hours via systemd timer.

**Phase 2 -- Insider Details**: Scrapes individual ticker pages for per-insider transactions. Auto-classifies insiders by title (CEO/CFO -> executive, 10% Owner -> fund, Director -> director) enabling executive-only filtering. Runs daily via systemd timer.

Data flows through: `HTTP request -> HTML parse -> Pydantic validation -> SQLite upsert`

```
openinsider-fetch-process/
|-- openinsider/                # Core package
|   |-- config.py               # Environment-based configuration
|   |-- models.py               # Pydantic models + insider classification
|   |-- parser.py               # BeautifulSoup HTML parser
|   |-- scraper.py              # HTTP scraper with retry logic
|   |-- database.py             # SQLite operations
|   `-- utils.py                # Logging, Discord alerts
|-- tests/                      # Test suite (coverage gate enforced at >=80%)
|-- deploy/                     # systemd units + install script
|-- run_scraper.py              # Phase 1 CLI
|-- run_insider_details.py      # Phase 2 CLI
|-- demo.py                     # Demo script
|-- schema.sql                  # Database schema
|-- requirements.txt            # Python dependencies
`-- .env.template               # Configuration template

See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment and operations guidance for Debian LXC.
```

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Configure
cp .env.template .env
# Edit .env if needed (defaults work for local development)

# Run Phase 1: scrape cluster buys
python run_scraper.py

# Run Phase 2: scrape insider details
python run_insider_details.py --all --limit 10

# View results
python demo.py
```

## Usage

### Phase 1: Cluster Buys

```bash
python run_scraper.py              # Scrape and save to database
python run_scraper.py --dry-run    # Preview without saving
python run_scraper.py --stats      # Show scrape history
python run_scraper.py --test       # Scrape but don't save
python run_scraper.py --debug      # Enable debug logging
```

### Phase 2: Insider Details

```bash
python run_insider_details.py --ticker ALLY           # Specific ticker
python run_insider_details.py --all --limit 10        # Top 10 recent cluster tickers
python run_insider_details.py --ticker AAPL --dry-run # Preview mode
python run_insider_details.py --all --debug           # Debug logging
```

### Python API

```python
from openinsider.database import OpenInsiderDB

db = OpenInsiderDB()

# Cluster buys
clusters = db.get_recent_clusters(limit=10)
aapl = db.get_cluster_by_ticker("AAPL", days=30)

# Individual insider transactions
insiders = db.get_insider_transactions("ALLY", days=90)

# Executive-only transactions (CEO, CFO, officers)
executives = db.get_executive_transactions(days=30)
for txn in executives:
    print(f"{txn['ticker']}: {txn['insider_name']} ({txn['insider_title']})")

# Scrape history
stats = db.get_scrape_stats(limit=5)
```

### SQL Queries

```sql
-- Biggest executive purchases
SELECT ticker, insider_name, insider_title, qty, value
FROM insider_transactions
WHERE insider_type = 'executive' AND trade_type LIKE 'P%' AND value > 100000
ORDER BY value DESC LIMIT 20;

-- Companies with most executive buying
SELECT ticker, COUNT(*) as exec_buys, SUM(qty) as total_shares
FROM insider_transactions
WHERE insider_type = 'executive' AND trade_type LIKE 'P%'
GROUP BY ticker ORDER BY exec_buys DESC;

-- Recent scrape history
SELECT * FROM scrape_log ORDER BY scrape_timestamp DESC LIMIT 10;

-- Active clusters
SELECT * FROM recent_clusters;
```

## Database Schema

**cluster_buys**: Aggregated cluster data with unique constraint on `(ticker, trade_date, filing_date)`. Updates when `insider_count` increases (more insiders join a cluster).

**insider_transactions**: Individual insider transactions with auto-classified `insider_type` (executive/fund/director/other).

**scrape_log**: Execution history for monitoring.

**recent_clusters**: View of the 100 most recent active clusters.

## Deployment (LXC)

The `deploy/` directory contains systemd service and timer units for the data-collection LXC.

### Install

```bash
# From the repo root on the target LXC
sudo ./deploy/install.sh
```

This will:
1. Create a `scraper` system user
2. Copy application to `/opt/trading/openinsider-fetch-process`
3. Set up a Python virtual environment
4. Install systemd timers (Phase 1 every 6h, Phase 2 daily at 01:30)

### Monitor

```bash
# Timer status
systemctl list-timers 'openinsider-*'

# Logs
journalctl -u openinsider-cluster.service
journalctl -u openinsider-details.service

# Manual run
systemctl start openinsider-cluster.service

# Application logs
tail -f /opt/trading/openinsider-fetch-process/logs/openinsider.log
```

## Configuration Reference

All settings are configured via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/openinsider.db` | SQLite database path |
| `SCRAPER_BASE_URL` | `http://openinsider.com` | OpenInsider base URL |
| `SCRAPER_TIMEOUT` | `30` | HTTP request timeout (seconds) |
| `USER_AGENT` | Mozilla/5.0... | HTTP User-Agent header |
| `RATE_LIMIT_DELAY` | `2.0` | Delay between Phase 2 requests (seconds) |
| `SCRAPER_MAX_RETRIES` | `3` | Max retry attempts on transient failures |
| `SCRAPER_RETRY_BACKOFF` | `2.0` | Base backoff delay for retries (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | `logs/openinsider.log` | Log file path |
| `LOG_MAX_BYTES` | `10485760` | Max log file size before rotation (10 MB) |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated log files to keep |
| `DISCORD_WEBHOOK_URL` | _(empty)_ | Discord webhook for alerts (optional) |
| `DISCORD_ALERT_THRESHOLD` | `10` | Min new clusters to trigger Discord alert |

## Development

```bash
# Run all tests
pytest -q

# Run with coverage
pytest --cov=openinsider

# Run specific test file
pytest tests/test_phase2.py -v

# Run with debug output
pytest -v -s
```

## License

MIT
