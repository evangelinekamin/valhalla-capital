#!/usr/bin/env bash
#
# Manual startup script for the Financial News Worker.
# Activates the virtual environment and runs the worker.
#
# Usage:
#   ./deploy/run.sh          # Run continuously
#   ./deploy/run.sh --once   # Run one cycle and exit
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
source "$PROJECT_DIR/venv/bin/activate"

# Run the worker, forwarding all arguments
exec python "$PROJECT_DIR/scripts/news_worker.py" "$@"
