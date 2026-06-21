#!/usr/bin/env bash
# Quick status check for overseer integration
# Usage: ssh <LAN_IP> /opt/substack-fetch-process/deploy/status.sh
#
# Returns JSON with pipeline metrics. Exit code 0 on success, 1 if no database.

INSTALL_DIR="/opt/substack-fetch-process"
DB="$INSTALL_DIR/newsletters.db"

if [ ! -f "$DB" ]; then
    echo '{"status": "no_database"}'
    exit 1
fi

sqlite3 "$DB" "
SELECT json_object(
    'status', 'ok',
    'emails', (SELECT COUNT(*) FROM emails),
    'images_total', (SELECT COUNT(*) FROM images),
    'images_processed', (SELECT COUNT(*) FROM images WHERE vision_output IS NOT NULL),
    'extracted', (SELECT COUNT(*) FROM extracted_data),
    'tickers', (SELECT COUNT(DISTINCT ticker) FROM ticker_updates),
    'total_cost_usd', COALESCE((SELECT ROUND(SUM(cost_usd), 4) FROM api_costs), 0),
    'last_fetch', (SELECT MAX(fetched_at) FROM emails),
    'history_id', (SELECT value FROM sync_state WHERE key='history_id')
);
"
