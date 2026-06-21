# Substack Newsletter Processing Pipeline

A pipeline for fetching, processing, and analyzing financial newsletters from Gmail/Substack. Extracts structured data including ticker picks, market sentiment, and financial metrics using AI-powered analysis.

## Features

- **Gmail Integration**: Fetch Substack newsletters via Gmail API with incremental sync
- **Image Processing**: Extract and analyze charts, graphs, and tables from newsletter images
- **AI-Powered Extraction**: Structure unstructured newsletter content into actionable data
- **Multiple Model Backends**: Switch between Anthropic API, Ollama, or llama.cpp
- **Cost Tracking**: Monitor API usage and costs with per-stage model selection
- **Deduplication**: Automatically detect and skip duplicate content
- **Incremental Processing**: Resume from where you left off
- **SQLite Storage**: Query historical data easily (WAL mode for concurrent access)
- **Graceful Shutdown**: SIGTERM/SIGINT handling for safe interruption
- **Structured Logging**: File + console logging with configurable levels
- **Discord Error Monitoring**: Real-time error notifications via Discord webhooks

## Quick Start

### 1. Installation

```bash
git clone <your-repo>
cd substack-fetch-process

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Gmail Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download the credentials as `credentials.json` and place in project root

### 3. API Key Setup

For Anthropic (default):
```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

Or copy `.env.example` to `.env` and fill in your key:
```bash
cp .env.example .env
```

`config.py` automatically loads `.env` on startup, so `orchestrate.py` and all stage scripts will read `ANTHROPIC_API_KEY` without requiring a manual `export` command.

For local models, see [Local Model Setup](#local-model-setup) below.

### 4. Discord Webhook Setup (Optional)

To receive error notifications in Discord:

1. Open Discord and navigate to the channel where you want to receive alerts
2. Click the gear icon (Edit Channel) → Integrations → Webhooks
3. Click "New Webhook" and copy the webhook URL
4. Add to your `.env` file:
```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
```

Or set it directly in `config.yaml`:
```yaml
discord:
  webhook_url: https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
```

Configure notification preferences in `config.yaml`:
- `notify_on_error: true` - Get notified when errors occur during processing
- `notify_on_warning: false` - Get notified for non-critical warnings
- `notify_on_start: false` - Get notified when the pipeline starts
- `notify_on_complete: false` - Get notified when the pipeline finishes successfully

### 5. Run the Pipeline

```bash
# Run everything
python orchestrate.py

# Or run specific stages
python orchestrate.py --stage fetch
python orchestrate.py --stage images
python orchestrate.py --stage vision
python orchestrate.py --stage extract

# Check status
python orchestrate.py --stage stats
```

## Architecture

The pipeline consists of 4 stages:

1. **Fetch** (`fetch_emails.py`): Pull emails from Gmail
2. **Images** (`process_images.py`): Download embedded images
3. **Vision** (`vision_process.py`): Analyze images with vision models
4. **Extract** (`extract_data.py`): Extract structured data from text + images

```
Gmail -> SQLite -> Images -> Vision API -> Structured JSON
```

All configuration flows through `config.yaml` via the `config.py` loader. All AI model calls go through the `model_client.py` abstraction layer.

## Configuration

Edit `config.yaml` to customize behavior. CLI arguments override config values.

```yaml
model:
  backend: anthropic  # or 'ollama', 'llamacpp'
  anthropic:
    vision_model: claude-haiku-3-5-20241022      # Cheaper for image descriptions
    extraction_model: claude-sonnet-4-5-20250929  # Full reasoning for extraction

gmail:
  query: from:substack.com

pipeline:
  batch_size: 10
  max_batches: null  # Limit for testing

logging:
  level: INFO
  file: pipeline.log  # null to disable

discord:
  enabled: true               # Enable/disable Discord notifications
  webhook_url: null           # Leave null to use DISCORD_WEBHOOK_URL env var
  notify_on_error: true       # Send notifications for errors
  notify_on_warning: false    # Send notifications for warnings
  notify_on_start: false      # Notify when pipeline starts
  notify_on_complete: false   # Notify when pipeline completes
```

### CLI Overrides

```bash
python orchestrate.py --model claude-haiku-3-5-20241022  # Override model for all stages
python orchestrate.py --batch-size 5 --max-batches 2     # Limit processing
python orchestrate.py --db /path/to/other.db             # Different database
python orchestrate.py --config /path/to/config.yaml      # Different config file
```

## Usage Examples

### Basic Usage

```bash
# Process all new newsletters
python orchestrate.py

# Test with limited batches
python orchestrate.py --max-batches 2 --batch-size 5
```

### Query Extracted Data

```sql
-- Using SQLite directly
sqlite3 newsletters.db

-- Get all high-confidence ticker picks
SELECT ticker, thesis, confidence FROM ticker_updates WHERE confidence='high';

-- Track a specific ticker over time
SELECT e.date, t.action, t.sentiment, t.thesis
FROM ticker_updates t
JOIN emails e ON t.email_id = e.id
WHERE t.ticker='AAPL'
ORDER BY e.date;

-- Check API costs
SELECT purpose, SUM(cost_usd), COUNT(*)
FROM api_costs
GROUP BY purpose;
```

### Using Python

```python
from config import load_config
from db_schema import init_db
import json

cfg = load_config()
conn = init_db(cfg.database_path)

rows = conn.execute('''
    SELECT e.subject, ed.content
    FROM emails e
    JOIN extracted_data ed ON e.id = ed.email_id
''').fetchall()

for subject, content in rows:
    data = json.loads(content)
    print(f"\n{subject}")
    print(f"Summary: {data['summary']}")
    for pick in data['ticker_picks']:
        print(f"  {pick['ticker']}: {pick['thesis']}")

conn.close()
```

## Deployment (Proxmox LXC)

This pipeline is designed to run on the data-collection LXC (<LAN_IP>) alongside other data acquisition services.

Suggested container map from your environment:

- `data-collection` (`<LAN_IP>`): this Substack pipeline + other inbound collectors
- `fmp` (`<LAN_IP>`): Financial Modeling Prep ingestion/cache
- `trading` (`<LAN_IP>`): broker execution / position management
- `overseer` (`<LAN_IP>`): orchestration, supervision, escalation
- `dashboard` (`<LAN_IP>`): monitoring and operator UI

### Prerequisites

- Debian LXC container
- Python 3.11+
- Gmail OAuth credentials (`credentials.json`)
- Anthropic API key

### Quick Deploy

```bash
# On the LXC, with the repo at /opt/substack-fetch-process:
sudo bash deploy/setup.sh

# Optional: run deployment preflight checks
bash deploy/preflight.sh /opt/substack-fetch-process

# Configure
vim /opt/substack-fetch-process/.env          # Set ANTHROPIC_API_KEY
cp credentials.json /opt/substack-fetch-process/

# Initial Gmail auth (interactive, one-time)
cd /opt/substack-fetch-process
sudo -u pipeline ./venv/bin/python orchestrate.py --stage fetch

# Verify
systemctl status substack-pipeline.timer
```

### systemd Service

The deployment includes a systemd timer that runs the pipeline at 6 AM and 6 PM daily:

```bash
# Check timer status
systemctl status substack-pipeline.timer

# Run manually
systemctl start substack-pipeline.service

# View logs
journalctl -u substack-pipeline.service -f

# Pipeline file logs
tail -f /opt/substack-fetch-process/pipeline.log
```

### Deployment Preflight Checks

Use the included script to verify host readiness before enabling timers:

```bash
bash deploy/preflight.sh /opt/substack-fetch-process
```

Checks include Python/sqlite3/systemd tooling, required config files, Gmail OAuth artifacts, and DB readability.

### Overseer Integration

The overseer at <LAN_IP> can check pipeline status via SSH:

```bash
ssh <LAN_IP> /opt/substack-fetch-process/deploy/status.sh
```

Returns JSON:
```json
{
  "status": "ok",
  "emails": 150,
  "images_total": 420,
  "images_processed": 418,
  "extracted": 148,
  "tickers": 35,
  "total_cost_usd": 1.2340,
  "last_fetch": "2026-02-12 06:00:01"
}
```

## Local Model Setup

### Option 1: Ollama

1. Install Ollama: https://ollama.ai
2. Pull a vision model:
   ```bash
   ollama pull llama3.2-vision
   ```
3. Update `config.yaml`:
   ```yaml
   model:
     backend: ollama
     ollama:
       model: llama3.2-vision
   ```

### Option 2: llama.cpp

1. Build llama.cpp with llava support
2. Start the server:
   ```bash
   ./server -m llava-v1.5-7b.gguf --port 8080
   ```
3. Update `config.yaml`:
   ```yaml
   model:
     backend: llamacpp
   ```

## Database Schema

### Tables

- **emails**: Newsletter metadata and HTML content
- **images**: Downloaded images with vision analysis
- **extracted_data**: Structured JSON extractions
- **ticker_updates**: Stock picks and updates (queryable)
- **api_costs**: Token usage and cost tracking
- **sync_state**: Gmail sync checkpoint

The database uses WAL journaling mode for concurrent read access (allows the overseer to query while the pipeline writes).

### Key Queries

```sql
-- Top mentioned tickers
SELECT ticker, COUNT(*) as mentions
FROM ticker_updates
GROUP BY ticker
ORDER BY mentions DESC;

-- Recent bullish picks
SELECT ticker, thesis, e.date
FROM ticker_updates t
JOIN emails e ON t.email_id = e.id
WHERE sentiment='bullish'
ORDER BY e.date DESC
LIMIT 10;

-- Cost breakdown by day
SELECT
  DATE(created_at) as date,
  SUM(cost_usd) as daily_cost
FROM api_costs
GROUP BY date
ORDER BY date DESC;
```

## Model Abstraction Layer

The `model_client.py` provides a unified interface for all model backends:

```python
from model_client import create_model_client

# Anthropic
client = create_model_client("anthropic", model="claude-sonnet-4-5-20250929")

# Ollama
client = create_model_client("ollama", model="llama3.2-vision")

# llama.cpp
client = create_model_client("llamacpp", base_url="http://localhost:8080")

# Same interface for all backends
response = client.generate_text("What is 2+2?")
print(response.text)
print(f"Tokens: {response.input_tokens} in, {response.output_tokens} out")
```

## Output Files

The pipeline generates:

- `newsletters.db`: SQLite database with all data
- `newsletter_data.json`: All extractions with metadata
- `ticker_history.json`: Ticker-centric view of picks
- `images/`: Downloaded newsletter images
- `pipeline.log`: Operational log file

## Cost Optimization

### Per-Stage Model Selection

The config supports different models per stage to optimize cost:

```yaml
model:
  anthropic:
    vision_model: claude-haiku-3-5-20241022      # $0.80/1M in -- good for image descriptions
    extraction_model: claude-sonnet-4-5-20250929  # $3.00/1M in -- needed for complex extraction
```

### Other Tips

1. **Process in batches** to monitor costs:
   ```bash
   python orchestrate.py --max-batches 2 --batch-size 10
   ```

2. **Switch to local models** for zero per-token costs:
   ```yaml
   model:
     backend: ollama
   ```

3. **Monitor costs**:
   ```bash
   sqlite3 newsletters.db "SELECT purpose, SUM(cost_usd) FROM api_costs GROUP BY purpose"
   ```

## Scheduling

### systemd Timer (Recommended)

The `deploy/` directory includes a systemd timer. See [Deployment](#deployment-proxmox-lxc).

### Cron (Alternative)

```bash
# Fetch new emails every hour
0 * * * * cd /opt/substack-fetch-process && ./venv/bin/python orchestrate.py --stage fetch

# Process everything daily at 2am
0 2 * * * cd /opt/substack-fetch-process && ./venv/bin/python orchestrate.py
```

## Troubleshooting

### Gmail OAuth Issues

If you get authentication errors:
```bash
rm token.json  # Force re-authentication
python orchestrate.py --stage fetch
```

### Image Download Failures

Some images may be behind paywalls or expire. The pipeline skips these and continues.

### Vision API Errors

The retry logic handles transient errors with exponential backoff. For persistent issues:
- Check your API key is set (`echo $ANTHROPIC_API_KEY`)
- Verify image format (JPEG, PNG, WebP supported)
- Check `pipeline.log` for detailed error messages

### Empty Extractions

If extraction returns empty data:
- Newsletter might not contain financial content
- Try a more powerful model (`--model claude-sonnet-4-5-20250929`)
- Check the HTML parsing by inspecting the database

### Discord Notifications Not Working

If you're not receiving Discord notifications:
- Verify the webhook URL is correct (test it with `curl`)
- Check that `discord.enabled: true` in `config.yaml`
- Ensure `discord.notify_on_error: true` if you want error notifications
- Check `pipeline.log` for Discord notification failures
- Test the webhook manually:
  ```bash
  curl -X POST "$DISCORD_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{"content": "Test notification from Substack pipeline"}'
  ```

## Development

### Project Structure

```
.
├── config.py            # Central configuration loader
├── config.yaml          # Pipeline configuration
├── db_schema.py         # Database schema and initialization
├── utils.py             # Retry logic, cost tracking, utilities
├── model_client.py      # Model abstraction layer (Anthropic/Ollama/llama.cpp)
├── discord_notifier.py  # Discord webhook error monitoring
├── fetch_emails.py      # Stage 1: Gmail fetching
├── process_images.py    # Stage 2: Image downloading
├── vision_process.py    # Stage 3: Vision analysis
├── extract_data.py      # Stage 4: Data extraction
├── orchestrate.py       # Main pipeline orchestrator
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── deploy/
    ├── setup.sh                     # LXC deployment script
    ├── preflight.sh                 # Host/config readiness checks
    ├── status.sh                    # Overseer status check (JSON output)
    ├── substack-pipeline.service    # systemd service
    └── substack-pipeline.timer      # systemd timer
```

## License

MIT
