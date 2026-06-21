# Yellowbrick Fetch Process

Production-oriented scraper for Yellowbrick institutional trading insights. It uses Playwright for authenticated page access, parses the embedded Next.js payloads, and stores normalized pitch data in SQLite.

## What this repository does

- Authenticates with exported Yellowbrick session cookies.
- Scrapes one or more feeds (`big_money`, `elite`).
- Normalizes data into immutable Pydantic models.
- Upserts pitch data and logs scrape outcomes into SQLite.
- Sends optional Discord alerts for failures and notable run outcomes.

---

## Requirements

- Python **3.10+**
- Linux (tested on Debian-like environments)
- Chromium runtime for Playwright
- Valid Yellowbrick cookies exported as JSON

## Quick start

### 1) Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Important**: Playwright requires system libraries to run Chromium. If you encounter errors like `libglib-2.0.so.0: cannot open shared object file`, install the system dependencies:

```bash
sudo ./install_playwright_deps.sh
```

This script will detect your OS and install the required libraries for Debian/Ubuntu or RHEL/CentOS/Fedora systems.

### 2) Configure

```bash
cp .env.template .env
```

Required values:
- `COOKIE_FILE`: path to exported cookie JSON.

Commonly used values:
- `DATABASE_PATH` (default `./data/yellowbrick.db`)
- `PLAYWRIGHT_HEADLESS` (default `true`)
- `DISCORD_WEBHOOK_URL` (optional)

### 3) Verify auth before first scrape

```bash
python run_scraper.py --test
```

### 4) Run scraper

```bash
# all feeds
python run_scraper.py

# single feed
python run_scraper.py --feed big_money
python run_scraper.py --feed elite

# debug + no writes
python run_scraper.py --debug --dry-run
```

---

## Deployment notes (Debian LXC)

### Minimal preflight checklist

Run these on the target container before enabling schedule automation:

```bash
python3 --version
source venv/bin/activate
python run_scraper.py --test
python run_scraper.py --dry-run --debug
pytest -q
```

### systemd timer setup

```bash
sudo cp deploy/yellowbrick-scraper.service /etc/systemd/system/
sudo cp deploy/yellowbrick-scraper.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable yellowbrick-scraper.timer
sudo systemctl start yellowbrick-scraper.timer
```

Check:

```bash
systemctl status yellowbrick-scraper.timer
systemctl list-timers yellowbrick-scraper.timer
```

### Optional log rotation

```bash
sudo cp deploy/yellowbrick-logrotate.conf /etc/logrotate.d/yellowbrick
```

### Cron alternative

```cron
0 8 * * * /opt/yellowbrick-fetch-process/run_scraper.sh >> /var/log/yellowbrick_cron.log 2>&1
```

---

## Runtime layout

- `run_scraper.py`: CLI entrypoint/orchestration
- `yellowbrick/authenticator.py`: cookie loading + validation
- `yellowbrick/scraper.py`: Playwright browser interaction
- `yellowbrick/parser.py`: extraction and normalization
- `yellowbrick/database.py`: SQLite persistence and scrape logs
- `yellowbrick/models.py`: immutable Pydantic models

---

## Data model summary

### `yellowbrick_pitches`
Main pitch table with upsert behavior by unique `pitch_id`.

### `yellowbrick_positions`
Position history tracking for updates over time.

### `yellowbrick_scrape_log`
Operational log table for scrape outcomes, counts, and timing.

Schema source: `schema.sql`.

---

## Operations & troubleshooting

### Authentication errors

1. Re-export cookies from a currently logged-in browser.
2. Confirm `COOKIE_FILE` path in `.env`.
3. Restrict cookie file permissions:

```bash
chmod 600 <cookie-file>
```

4. Re-test auth:

```bash
python run_scraper.py --test
```

### Browser launch errors

If you see errors like:
- `libglib-2.0.so.0: cannot open shared object file`
- `Target page, context or browser has been closed`
- `It looks like you are using Playwright Sync API inside the asyncio loop`

This means Playwright's Chromium is missing system dependencies. Fix by installing them:

```bash
sudo ./install_playwright_deps.sh
```

After installing, re-run the scraper:

```bash
python run_scraper.py --test
python run_scraper.py --dry-run
```

### Scrape returns zero pitches

Run in debug dry-run mode:

```bash
python run_scraper.py --debug --dry-run
```

Then verify:
- feed URLs in `yellowbrick/config.py`
- cookie validity
- whether Yellowbrick changed page structure

### Database checks

```bash
sqlite3 data/yellowbrick.db "PRAGMA integrity_check;"
sqlite3 data/yellowbrick.db ".schema yellowbrick_pitches"
sqlite3 data/yellowbrick.db "SELECT COUNT(*) FROM yellowbrick_pitches;"
```

---

## Testing

```bash
pytest -q
pytest tests/ --cov=yellowbrick --cov-report=html
```

---

## Security reminders

- Never commit `.env` or cookie files.
- Keep cookie files at `0600` permissions.
- Use encrypted backups for persisted databases.
- Keep containers patched and clocks synchronized (TLS/auth timing matters).

## License

Private use only.
