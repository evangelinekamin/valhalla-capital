#!/usr/bin/env bash
# Install Playwright System Dependencies
# This script installs the required system libraries for Playwright Chromium

set -euo pipefail

echo "Installing Playwright system dependencies..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Cannot detect OS"
    exit 1
fi

case "$OS" in
    ubuntu|debian)
        echo "Detected Debian/Ubuntu system"
        apt-get update
        apt-get install -y \
            libnss3 \
            libnspr4 \
            libatk1.0-0 \
            libatk-bridge2.0-0 \
            libcups2 \
            libdrm2 \
            libdbus-1-3 \
            libatspi2.0-0 \
            libx11-6 \
            libxcomposite1 \
            libxdamage1 \
            libxext6 \
            libxfixes3 \
            libxrandr2 \
            libgbm1 \
            libxkbcommon0 \
            libpango-1.0-0 \
            libcairo2 \
            libasound2 \
            libglib2.0-0
        ;;
    centos|rhel|fedora|rocky|almalinux)
        echo "Detected RHEL/CentOS/Fedora system"
        yum install -y \
            nss \
            nspr \
            atk \
            at-spi2-atk \
            cups-libs \
            libdrm \
            dbus-libs \
            at-spi2-core \
            libX11 \
            libXcomposite \
            libXdamage \
            libXext \
            libXfixes \
            libXrandr \
            mesa-libgbm \
            libxkbcommon \
            pango \
            cairo \
            alsa-lib \
            glib2
        ;;
    *)
        echo "Unsupported OS: $OS"
        echo "Please install Playwright dependencies manually."
        exit 1
        ;;
esac

echo ""
echo "Playwright system dependencies installed successfully!"
echo ""
echo "Next steps:"
echo "1. Activate your virtual environment: source venv/bin/activate"
echo "2. Install Playwright browsers: playwright install chromium"
echo "3. Run the scraper: ./run_scraper.sh"
