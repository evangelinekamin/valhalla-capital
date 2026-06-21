#!/usr/bin/env bash
# Yellowbrick Scraper - Run Script
# Used by cron or systemd to execute the scraper

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source venv/bin/activate

# Run scraper
python run_scraper.py "$@"
