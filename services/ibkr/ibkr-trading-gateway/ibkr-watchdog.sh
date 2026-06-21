#!/bin/bash
# IBKR Gateway Watchdog
# Checks if the trading-service can actually reach the IB Gateway TWS socket.
# If the health check fails, restarts ib-gateway then trading-service.

LOG_TAG="ibkr-watchdog"
COMPOSE_DIR="/opt/ibkr-trading-gateway"

log() {
    logger -t "$LOG_TAG" "$1"
    echo "$(date -Iseconds) $1"
}

# Run the existing health_check.py inside trading-service (uses clientId=999)
if docker exec trading-service python /app/scripts/health_check.py 2>/dev/null; then
    log "OK: IBKR connectivity healthy"
    exit 0
fi

log "WARN: Health check failed, verifying..."

# Double-check to avoid false positives
sleep 5
if docker exec trading-service python /app/scripts/health_check.py 2>/dev/null; then
    log "OK: Health check passed on retry, transient issue"
    exit 0
fi

log "ERROR: IBKR connection confirmed dead. Restarting ib-gateway..."

cd "$COMPOSE_DIR"
docker-compose restart ib-gateway

# Wait for ib-gateway to become healthy (up to 3 minutes, it has 120s start_period)
for i in $(seq 1 18); do
    sleep 10
    STATUS=$(docker inspect --format={{.State.Health.Status}} ib-gateway 2>/dev/null)
    if [ "$STATUS" = "healthy" ]; then
        log "OK: ib-gateway is healthy after restart"
        break
    fi
    log "Waiting for ib-gateway... ($i/18, status=$STATUS)"
done

STATUS=$(docker inspect --format={{.State.Health.Status}} ib-gateway 2>/dev/null)
if [ "$STATUS" != "healthy" ]; then
    log "ERROR: ib-gateway did not become healthy after restart"
    exit 1
fi

# Restart trading-service so it reconnects
log "Restarting trading-service to reconnect..."
docker-compose restart trading-service

sleep 15

# Final verification
if docker exec trading-service python /app/scripts/health_check.py 2>/dev/null; then
    log "OK: Full recovery successful"
    exit 0
else
    log "ERROR: Recovery failed — trading-service still cannot reach IB Gateway"
    exit 1
fi
