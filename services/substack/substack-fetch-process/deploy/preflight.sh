#!/usr/bin/env bash
# Preflight checks for Debian LXC deployments.
# Usage: bash deploy/preflight.sh [/opt/substack-fetch-process]
set -euo pipefail

INSTALL_DIR="${1:-/opt/substack-fetch-process}"
STATUS=0

pass() { echo "✅ $1"; }
warn() { echo "⚠️  $1"; }
fail() { echo "❌ $1"; STATUS=1; }

command -v python3 >/dev/null 2>&1 && pass "python3 present ($(python3 --version 2>/dev/null))" || fail "python3 is missing"
command -v sqlite3 >/dev/null 2>&1 && pass "sqlite3 present" || fail "sqlite3 is missing"
command -v systemctl >/dev/null 2>&1 && pass "systemd tooling present" || warn "systemctl not available in this environment"

if [ -d "$INSTALL_DIR" ]; then
  pass "install directory exists: $INSTALL_DIR"
else
  fail "install directory missing: $INSTALL_DIR"
fi

if [ -f "$INSTALL_DIR/config.yaml" ]; then
  pass "config.yaml found"
else
  fail "config.yaml not found in $INSTALL_DIR"
fi

if [ -f "$INSTALL_DIR/.env" ]; then
  if rg -q '^ANTHROPIC_API_KEY=' "$INSTALL_DIR/.env"; then
    pass ".env contains ANTHROPIC_API_KEY entry"
  else
    warn ".env exists but ANTHROPIC_API_KEY entry was not found"
  fi
else
  warn ".env missing (copy from .env.example)"
fi

if [ -f "$INSTALL_DIR/credentials.json" ]; then
  pass "credentials.json found"
else
  warn "credentials.json missing (required for Gmail OAuth)"
fi

if [ -f "$INSTALL_DIR/token.json" ]; then
  pass "token.json present (OAuth already completed)"
else
  warn "token.json missing (first fetch run will require interactive auth)"
fi

if [ -f "$INSTALL_DIR/newsletters.db" ]; then
  pass "database present"
  set +e
  sqlite3 "$INSTALL_DIR/newsletters.db" 'SELECT COUNT(*) FROM emails;' >/dev/null 2>&1
  DB_CHECK=$?
  set -e
  if [ "$DB_CHECK" -eq 0 ]; then
    pass "database readable"
  else
    fail "database exists but could not be queried"
  fi
else
  warn "database not present yet (normal before first successful run)"
fi

exit "$STATUS"
