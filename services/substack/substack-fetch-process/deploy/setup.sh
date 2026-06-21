#!/usr/bin/env bash
# Deployment script for the data-collection LXC (<LAN_IP>)
# Usage: sudo bash deploy/setup.sh
set -euo pipefail

INSTALL_DIR="/opt/substack-fetch-process"
SERVICE_USER="pipeline"

echo "=== Substack Pipeline Setup on $(hostname) ==="

# Create service user if it doesn't exist
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user: $SERVICE_USER"
    useradd --system --home-dir "$INSTALL_DIR" --shell /bin/false "$SERVICE_USER"
fi

# Ensure install directory exists and has latest code
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR" && git pull
else
    echo "Install directory should contain the repository."
    echo "Clone or copy the repo to $INSTALL_DIR first."
    exit 1
fi

# Set up Python virtual environment
echo "Setting up Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt --quiet

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">>> Created .env from template. Edit it with your API key:"
    echo "    $INSTALL_DIR/.env"
fi

# Ensure data directories exist
mkdir -p images

# Set ownership
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Install systemd units
echo "Installing systemd service and timer..."
cp deploy/substack-pipeline.service /etc/systemd/system/
cp deploy/substack-pipeline.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable substack-pipeline.timer
systemctl start substack-pipeline.timer

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your ANTHROPIC_API_KEY:"
echo "     vim $INSTALL_DIR/.env"
echo ""
echo "  2. Place Gmail OAuth credentials:"
echo "     cp credentials.json $INSTALL_DIR/"
echo ""
echo "  3. Run initial Gmail auth (interactive, one-time):"
echo "     cd $INSTALL_DIR && sudo -u $SERVICE_USER ./venv/bin/python orchestrate.py --stage fetch"
echo ""
echo "Useful commands:"
echo "  Timer status:  systemctl status substack-pipeline.timer"
echo "  Run now:       systemctl start substack-pipeline.service"
echo "  View logs:     journalctl -u substack-pipeline.service -f"
echo "  Pipeline logs: tail -f $INSTALL_DIR/pipeline.log"
