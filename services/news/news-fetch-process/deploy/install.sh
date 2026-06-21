#!/usr/bin/env bash
#
# Install script for the Financial News Worker.
# Resolves the project directory from this script's location and deploys
# the systemd service file and cron job with correct paths.
#
# Usage:
#   sudo ./deploy/install.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Financial News Worker Install ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# --- 1. Create required directories ---
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/alerts"
mkdir -p "$PROJECT_DIR/data"
echo "[OK] Created logs, alerts, and data directories"

# --- 2. Create virtual environment if missing ---
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/venv"
    "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
    echo "[OK] Virtual environment created and dependencies installed"
else
    echo "[OK] Virtual environment already exists"
fi

# --- 3. Install systemd service ---
echo ""
echo "--- Systemd Service ---"
sed "s|@@PROJECT_DIR@@|${PROJECT_DIR}|g" \
    "$SCRIPT_DIR/news-worker.service" \
    > /etc/systemd/system/news-worker.service

systemctl daemon-reload
systemctl enable news-worker
echo "[OK] Service installed and enabled"
echo "     Start with: sudo systemctl start news-worker"

# --- 4. Install cron job ---
echo ""
echo "--- Cron Job ---"
CRON_LINE=$(sed "s|@@PROJECT_DIR@@|${PROJECT_DIR}|g" "$SCRIPT_DIR/daily-rotation.cron" \
    | grep -v '^#' | grep -v '^$' | head -1)

# Remove any existing rotation entry, then add the new one
( crontab -l 2>/dev/null | grep -v 'daily_rotation.py' ; echo "$CRON_LINE" ) | crontab -
echo "[OK] Cron job installed:"
echo "     $CRON_LINE"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit config/feeds.json with your API keys"
echo "  2. sudo systemctl start news-worker"
echo "  3. journalctl -u news-worker -f"
