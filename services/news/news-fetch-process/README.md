# Financial News Monitor

Real-time financial news monitoring system that fetches RSS feeds from major financial news sources, classifies articles by urgency using Claude AI, and tracks critical market alerts with Discord notifications.

## Features

- Monitors 7 financial news sources (Bloomberg, Reuters, Yahoo Finance, WSJ, FT, BBC, Nasdaq)
- AI-powered article classification (CRITICAL / IMPORTANT / ROUTINE) using Claude Haiku
- Market-hours-aware polling (5 min during trading, 30 min off-market)
- Headline deduplication with configurable lookback window
- Critical alert storage with acknowledgment tracking and daily archival
- Discord webhook notifications for critical alerts, errors, and daily summaries
- CLI dashboard for viewing current alert status
- systemd service and cron job for automated deployment

## Prerequisites

- Python 3.11+
- [Anthropic API key](https://console.anthropic.com/)
- (Optional) Discord webhook URL for notifications

## Installation

```bash
git clone <repository-url>
cd news-fetch-process
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

All configuration lives in `config/feeds.json`.

### API Keys

Set your keys directly in the config file:

```json
{
  "anthropic_api_key": "sk-ant-your-key-here",
  "discord_webhook_url": "https://discord.com/api/webhooks/...",
  ...
}
```

Environment variables (`ANTHROPIC_API_KEY`, `DISCORD_WEBHOOK_URL`) are used as fallbacks if the config fields are empty. See `.env.example` for the format.

### Feed Configuration

Each feed in the `feeds` array has:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name for the feed |
| `url` | string | RSS feed URL |
| `priority` | int | Processing priority (1 = highest) |
| `enabled` | bool | Whether to process this feed |

### Other Settings

| Field | Description |
|-------|-------------|
| `market_hours` | Timezone, trading days, start/end times, polling intervals |
| `deduplication` | Enable/disable, lookback window (hours), similarity threshold |
| `max_articles_per_feed` | Maximum articles to process per feed per cycle |

## Usage

### One-shot (run once and exit)

```bash
source venv/bin/activate
python scripts/news_worker.py --once
```

### Continuous (manual)

```bash
./deploy/run.sh
```

### Automated Deployment (systemd + cron)

```bash
# One-step install: sets up systemd service and cron job
sudo ./deploy/install.sh

# Start the service
sudo systemctl start news-worker

# View logs
journalctl -u news-worker -f
```

The install script automatically detects the project directory, creates required directories, installs the systemd service with correct paths, and enables the daily alert rotation cron job. It is safe to re-run after moving the project to a new location.

### CLI Dashboard

```bash
python scripts/dashboard.py
```

### Query Alerts Programmatically

```bash
python scripts/overseer_news_client.py
```

## Discord Webhook Setup

1. Open your Discord server settings
2. Go to **Integrations > Webhooks**
3. Click **New Webhook**, name it, and select a channel
4. Copy the webhook URL
5. Paste it into `config/feeds.json` under `"discord_webhook_url"`

Notifications are sent for:

| Event | Color | Frequency |
|-------|-------|-----------|
| Critical article alert | Red | Per event |
| Feed processing error | Yellow | Per error |
| Main loop error | Orange | Per error |
| Worker startup | Green | On start |
| Worker shutdown | Blue | On stop |
| Daily summary | Blue | Once per day |

If no webhook URL is configured, notifications are silently disabled.

## Project Structure

```
news-fetch-process/
├── alerts/
│   ├── archive/              # Daily archived alerts
│   └── critical_alerts.json  # Today's critical alerts
├── config/
│   └── feeds.json            # All configuration (feeds, keys, market hours)
├── deploy/
│   ├── daily-rotation.cron   # Cron job template for daily archival
│   ├── install.sh            # Automated install (systemd + cron)
│   ├── news-worker.service   # systemd service unit template
│   └── run.sh                # Manual startup script
├── scripts/
│   ├── alert_manager.py      # Alert CRUD and archival
│   ├── dashboard.py          # CLI alert dashboard
│   ├── daily_rotation.py     # Daily archival trigger
│   ├── discord_notifier.py   # Discord webhook notifications
│   ├── news_worker.py        # Main worker (RSS fetch, AI classify)
│   └── overseer_news_client.py  # Alert query client
├── .env.example              # Environment variable fallback template
├── requirements.txt
└── README.md
```

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `news_worker.py` | Main program: fetches feeds, classifies articles, stores critical alerts |
| `alert_manager.py` | JSON-based alert storage with atomic writes and daily archival |
| `discord_notifier.py` | Fail-safe Discord webhook notification sender |
| `dashboard.py` | CLI view of today's alerts and statistics |
| `daily_rotation.py` | Archives previous day's alerts and resets for new day |
| `overseer_news_client.py` | Client for querying and acknowledging alerts programmatically |
