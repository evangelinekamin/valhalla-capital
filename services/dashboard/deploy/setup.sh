#!/usr/bin/env bash
# ============================================================
# Valhalla Capital — Deployment Script
# Run on the dashboard LXC (<LAN_IP>)
#
# Usage:
#   sudo bash deploy/setup.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/valhalla-capital"
SVC_USER="dashboard"
PYTHON="python3"

echo "=== Valhalla Capital Deployment ==="
echo ""

# --- System deps ---
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git openssh-client >/dev/null

# --- Service user ---
echo "[2/6] Creating service user..."
if ! id "$SVC_USER" &>/dev/null; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SVC_USER"
fi

# --- App directory ---
echo "[3/6] Setting up application directory..."
mkdir -p "$APP_DIR"
# If running from repo, copy files. Otherwise assume they're already there.
if [ -f "$(dirname "$0")/../requirements.txt" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
    rsync -a --exclude='.git' --exclude='.ssh' --exclude='venv' \
        --exclude='*.db' --exclude='__pycache__' \
        --exclude='cascade-session-*.md' \
        "$SCRIPT_DIR/" "$APP_DIR/"
fi

# --- Virtual environment ---
echo "[4/6] Setting up Python virtual environment..."
$PYTHON -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# --- SSH keys for health checks ---
echo "[5/6] Checking SSH key setup..."
SSH_DIR="$APP_DIR/.ssh"
if [ ! -f "$SSH_DIR/id_ed25519" ]; then
    mkdir -p "$SSH_DIR"
    ssh-keygen -t ed25519 -f "$SSH_DIR/id_ed25519" -N "" -q
    touch "$SSH_DIR/known_hosts"
    chown -R "$SVC_USER:$SVC_USER" "$SSH_DIR"
    chmod 700 "$SSH_DIR"
    chmod 600 "$SSH_DIR/id_ed25519"
    chmod 600 "$SSH_DIR/known_hosts"
    echo ""
    echo "  SSH public key generated. Add this to other LXC containers:"
    echo "  ────────────────────────────────────────────────────────────"
    cat "$SSH_DIR/id_ed25519.pub"
    echo "  ────────────────────────────────────────────────────────────"
    echo "  Copy to: ~/.ssh/authorized_keys on each target host"
    echo ""
else
    touch "$SSH_DIR/known_hosts"
    chown "$SVC_USER:$SVC_USER" "$SSH_DIR/known_hosts"
    chmod 600 "$SSH_DIR/known_hosts"
    echo "  SSH key already exists."
fi

# --- Permissions ---
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"

# --- systemd ---
echo "[6/6] Installing systemd services..."
cp "$APP_DIR/deploy/valhalla-capital.service" /etc/systemd/system/
cp "$APP_DIR/deploy/valhalla-capital-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable valhalla-capital.service
systemctl enable valhalla-capital-worker.service
systemctl restart valhalla-capital-worker.service
systemctl restart valhalla-capital.service

echo ""
echo "=== Valhalla Capital is live ==="
echo "  URL:     http://<LAN_IP>:8050"
echo "  Web:     systemctl status valhalla-capital"
echo "  Worker:  systemctl status valhalla-capital-worker"
echo "  Logs:    journalctl -u valhalla-capital -f"
echo "  Worker:  journalctl -u valhalla-capital-worker -f"
echo ""
echo "  Next steps:"
echo "  1. Add SSH public key to other LXC containers for health checks"
echo "  2. Point your nginx proxy at this address"
echo "  3. Set up Cloudflare DDNS for external access"
echo ""
