#!/bin/bash
# Daily backup of valhalla services to Backblaze B2 via restic.
# Scheduled by valhalla-backup.timer at 03:00 UTC.
# Containers that aren't running are silently skipped — safe during migration.

set -euo pipefail

set -a; source /opt/valhalla/secrets/b2.env; set +a
export RESTIC_PASSWORD_FILE=/opt/valhalla/secrets/restic-password

DUMP_DIR=$(mktemp -d /tmp/valhalla-backup.XXXXXX)
trap 'rm -rf "$DUMP_DIR"' EXIT

dump_pg() {
  local container=$1 user=$2 db=$3
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    docker exec "$container" pg_dump -U "$user" -d "$db" > "$DUMP_DIR/${container}.sql" 2>/dev/null
    echo "dumped $container ($(wc -c < "$DUMP_DIR/${container}.sql") bytes)"
  fi
}

dump_pg overseer-postgres overseer overseer
dump_pg trading-postgres trading trading
dump_pg miniflux-db miniflux miniflux
dump_pg processing-db postgres postgres

if docker ps --format '{{.Names}}' | grep -q '^fmp-mysql$' && [ -f /opt/valhalla/secrets/fmp-mysql.env ]; then
  set -a; source /opt/valhalla/secrets/fmp-mysql.env; set +a
  docker exec fmp-mysql mysqldump --user=root --password="$MYSQL_ROOT_PASSWORD" --all-databases > "$DUMP_DIR/fmp.sql" 2>/dev/null
  echo "dumped fmp-mysql ($(wc -c < "$DUMP_DIR/fmp.sql") bytes)"
fi

restic backup \
  --tag scheduled --tag "$(date -u +%Y%m%d)" \
  /opt/valhalla/data \
  /opt/valhalla/secrets \
  "$DUMP_DIR"

restic forget \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 12 \
  --prune

echo "backup complete $(date -u)"
