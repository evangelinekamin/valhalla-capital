# Quick Start Guide

Get the IBKR Trading Gateway up and running in 5 minutes!

## Prerequisites

- Docker and Docker Compose installed
- Interactive Brokers account (paper or live)
- Your IBKR credentials

## Step 1: Configure Environment

Edit the `.env.example` file with your credentials and save as `.env`:

```bash
# Required: Your IBKR credentials
IBKR_USERNAME=your_username_here
IBKR_PASSWORD=your_password_here

# Required: Database password
POSTGRES_PASSWORD=choose_a_secure_password

# Discord webhook is already configured
# VNC password is already set (secure random)
```

## Step 2: Start Services

```bash
# Start all services (IB Gateway, PostgreSQL, Trading Service)
docker-compose up -d

# Check logs
docker-compose logs -f trading-service
```

## Step 3: Initialize Database

```bash
# Wait for PostgreSQL to be ready (30 seconds)
sleep 30

# Run database migrations
docker-compose exec trading-service alembic upgrade head
```

## Step 4: Verify Everything Works

```bash
# Check service health
docker-compose ps

# Should see all services "healthy"
```

## Step 5: Submit a Test Trade

Create a test trade request file:

```bash
cat > ./shared/trade_requests/test_trade.json << 'EOF'
{
  "request_id": "123e4567-e89b-12d3-a456-426614174000",
  "timestamp": "2026-01-30T15:00:00Z",
  "ticker": "AAPL",
  "action": "BUY",
  "analysis": {
    "win_probability": 0.65,
    "expected_gain_pct": 0.15,
    "expected_loss_pct": -0.07,
    "confidence": 0.85
  },
  "reasoning": "Test trade to verify system functionality"
}
EOF
```

Within seconds, you should see:
- Log output processing the trade
- Result file in `./shared/trade_results/`
- Portfolio state in `./shared/portfolio_state/current.json`
- Discord notification (if enabled)

## Monitoring

### View Logs
```bash
# All services
docker-compose logs -f

# Just trading service
docker-compose logs -f trading-service

# Just IB Gateway
docker-compose logs -f ib-gateway
```

### View IB Gateway (VNC)
```bash
# Connect with VNC viewer to: localhost:5900
# Password: (from .env.example VNC_PASSWORD)
```

### Check Database
```bash
docker-compose exec postgres psql -U trading -d trading -c "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 5;"
```

### Portfolio State
```bash
cat ./shared/portfolio_state/current.json | jq
```

## Troubleshooting

### IB Gateway Won't Connect
```bash
# Restart IB Gateway
docker-compose restart ib-gateway

# Check logs
docker-compose logs ib-gateway
```

### Database Issues
```bash
# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d
sleep 30
docker-compose exec trading-service alembic upgrade head
```

### Panic Mode Stuck
```bash
docker-compose exec trading-service python scripts/manual_panic_reset.py
```

## Next Steps

1. **Paper Trading**: Test with paper account for 50+ trades
2. **Review Results**: Check `./shared/trade_results/` and database
3. **Adjust Settings**: Modify `.env` risk parameters if needed
4. **Go Live**: Change `TRADING_MODE=live` and `DRY_RUN_MODE=false` (CAREFULLY!)

## Important Notes

- **Paper Mode**: Default is paper trading (`TRADING_MODE=paper`, `DRY_RUN_MODE=true`)
- **Market Hours**: Only trades 9:30 AM - 4:00 PM ET on weekdays
- **Position Limits**: Max 20% per position, $30 minimum, $2000 maximum
- **Safety**: Panic mode halts all trading if daily loss > 3%

## Support

- Check logs: `docker-compose logs -f`
- Health checks: `docker-compose ps`
- Database queries: See README.md for SQL examples
- Emergency halt: Panic button triggers automatically or manually

---

**Remember**: Start with paper trading! Don't risk real money until you've validated the system thoroughly.
