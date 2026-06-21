#!/bin/bash

# Backup script for Nitter, Miniflux, and Processing Database
# Usage: ./backup.sh
# Cron: 0 2 * * * /path/to/twitter-fetch-process/backup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/backups"
LOG_FILE="$BACKUP_DIR/backup.log"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "Starting backup at $DATE"
log "========================================="

# Backup Miniflux PostgreSQL database
log "Backing up Miniflux database..."
if docker exec miniflux-db pg_dump -U miniflux miniflux | gzip > "$BACKUP_DIR/miniflux_$DATE.sql.gz" 2>> "$LOG_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/miniflux_$DATE.sql.gz" | cut -f1)
    log "✓ Miniflux database backup completed ($BACKUP_SIZE)"
else
    log "✗ Miniflux database backup failed"
    exit 1
fi

# Backup Processing Database (tweets database)
log "Backing up Processing database (tweets)..."
if docker exec processing-db pg_dump -U postgres twitter_data | gzip > "$BACKUP_DIR/processing_$DATE.sql.gz" 2>> "$LOG_FILE"; then
    PROCESSING_SIZE=$(du -h "$BACKUP_DIR/processing_$DATE.sql.gz" | cut -f1)
    log "✓ Processing database backup completed ($PROCESSING_SIZE)"
else
    log "✗ Processing database backup failed"
    exit 1
fi

# Optional: Backup Nitter Redis data (mostly cache, usually not critical)
log "Backing up Nitter Redis data..."
if docker run --rm --volumes-from nitter-redis -v "$BACKUP_DIR:/backup" alpine \
    tar czf "/backup/nitter-redis_$DATE.tar.gz" /data 2>> "$LOG_FILE"; then
    REDIS_SIZE=$(du -h "$BACKUP_DIR/nitter-redis_$DATE.tar.gz" | cut -f1)
    log "✓ Nitter Redis backup completed ($REDIS_SIZE)"
else
    log "✗ Nitter Redis backup failed (non-critical)"
fi

# Clean up old backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
DELETED_MINIFLUX=$(find "$BACKUP_DIR" -name "miniflux_*.sql.gz" -mtime +$RETENTION_DAYS -type f | wc -l)
DELETED_PROCESSING=$(find "$BACKUP_DIR" -name "processing_*.sql.gz" -mtime +$RETENTION_DAYS -type f | wc -l)
DELETED_REDIS=$(find "$BACKUP_DIR" -name "nitter-redis_*.tar.gz" -mtime +$RETENTION_DAYS -type f | wc -l)

find "$BACKUP_DIR" -name "miniflux_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "processing_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "nitter-redis_*.tar.gz" -mtime +$RETENTION_DAYS -delete

log "Deleted $DELETED_MINIFLUX old Miniflux backups, $DELETED_PROCESSING old Processing backups, and $DELETED_REDIS old Redis backups"

# Clean up old log entries (keep last 30 days)
if [ -f "$LOG_FILE" ]; then
    TEMP_LOG=$(mktemp)
    tail -n 1000 "$LOG_FILE" > "$TEMP_LOG" 2>/dev/null || true
    mv "$TEMP_LOG" "$LOG_FILE"
fi

# List current backups
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -type f \( -name "miniflux_*.sql.gz" -o -name "processing_*.sql.gz" -o -name "nitter-redis_*.tar.gz" \) | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

log "✓ Backup completed successfully"
log "Total backups: $TOTAL_BACKUPS | Total size: $TOTAL_SIZE"
log "Backups stored in: $BACKUP_DIR"
log "Log file: $LOG_FILE"
log "========================================="
log ""
