#!/usr/bin/env bash
set -euo pipefail

# OpenInsider scraper deployment for data-collection LXC (<LAN_IP>)
# Installs the application and enables systemd timers.
#
# Usage: sudo ./install.sh

APP_DIR="/opt/trading/openinsider-fetch-process"
SERVICE_USER="scraper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== OpenInsider Scraper Deployment ==="

# Ensure running as root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo ./install.sh)"
    exit 1
fi

# Create service user if it doesn't exist
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir /opt/trading "$SERVICE_USER"
    echo "Created system user: $SERVICE_USER"
fi

# Set up application directory
mkdir -p "$APP_DIR"/{data,logs}

# Copy application files
rsync -a --exclude='.git' --exclude='venv' --exclude='data/*.db' \
    --exclude='logs/*.log*' --exclude='htmlcov' --exclude='.pytest_cache' \
    --exclude='__pycache__' --exclude='*.egg-info' \
    "$REPO_DIR/" "$APP_DIR/"

# Create virtual environment and install dependencies
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
"$APP_DIR/venv/bin/pip" install -e "$APP_DIR" --quiet

# Create .env from template if it doesn't exist
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.template" "$APP_DIR/.env"
    echo ""
    echo "Created .env from template -- review and configure before first run:"
    echo "  $APP_DIR/.env"
fi

# Set ownership
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"

# Install systemd units
cp "$APP_DIR/deploy/openinsider-cluster.service" /etc/systemd/system/
cp "$APP_DIR/deploy/openinsider-cluster.timer" /etc/systemd/system/
cp "$APP_DIR/deploy/openinsider-details.service" /etc/systemd/system/
cp "$APP_DIR/deploy/openinsider-details.timer" /etc/systemd/system/

systemctl daemon-reload

# Enable and start timers
systemctl enable --now openinsider-cluster.timer
systemctl enable --now openinsider-details.timer

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Timers enabled:"
systemctl list-timers 'openinsider-*' --no-pager
echo ""
echo "Commands:"
echo "  Manual run:    systemctl start openinsider-cluster.service"
echo "  View logs:     journalctl -u openinsider-cluster.service"
echo "  Timer status:  systemctl list-timers 'openinsider-*'"
echo "  Disable:       systemctl disable --now openinsider-cluster.timer"
