# Valhalla Capital

> *"Time to mix drinks and save lives."*

Fund monitoring terminal for an autonomous trading system. Swiss typographic style meets VA-11 Hall-A warmth.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Valhalla Capital Dashboard (<LAN_IP>:8050)        │
│  FastAPI + Jinja2 + htmx                            │
│                                                     │
│  Polls health endpoints every 60s:                  │
│  ├── data-collection  <LAN_IP>                │
│  │   ├── Twitter Monitor    :8082/health            │
│  │   ├── Substack Pipeline  (SSH status.sh)         │
│  │   ├── Yellowbrick Scraper                        │
│  │   ├── News Monitor                               │
│  │   └── OpenInsider Scraper                        │
│  ├── fmp              <LAN_IP>                │
│  │   └── FMP Data Client    :8000/health            │
│  ├── trading          <LAN_IP>                │
│  │   ├── IB Gateway                                 │
│  │   └── Trade Executor                             │
│  └── overseer         <LAN_IP>                │
│      └── Overseer                                   │
│                                                     │
│  Local storage: SQLite (health snapshots, stats)    │
└─────────────────────────────────────────────────────┘
```

The deployment now runs as two processes:
- `valhalla-capital.service`: web app only
- `valhalla-capital-worker.service`: health checks, pruning, and portfolio snapshots

## Quick Start

```bash
# On the dashboard LXC (<LAN_IP>):
git clone <repo> /opt/valhalla-capital
cd /opt/valhalla-capital
sudo bash deploy/setup.sh
```

The setup script handles: system deps, Python venv, SSH key generation, systemd service installation.

## Development

```bash
cp .env.example .env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8050
```

Background jobs in development can be run separately with:

```bash
python -m app.worker
```

## Service Status Labels

| Status     | Meaning                      | Color |
|-----------|------------------------------|-------|
| Served    | Healthy, all nominal         | Cyan  |
| Mixing    | Degraded, responding w/issues| Amber |
| 86'd      | Down, not responding         | Pink  |
| On Order  | Not yet checked / no endpoint| Gray  |
| Last Call | Approaching resource limits  | Amber |

## Adding New Services

Edit `app/config.py` and add a `ServiceDef` to the `SERVICES` list:

```python
ServiceDef(
    name="My New Service",
    host="192.168.86.XXX",
    port=8000,
    description="What this service does",
    health_url="http://192.168.86.XXX:8000/health",
    group="data",  # data | execution | brain | infrastructure
)
```

The dashboard will start polling it on the next check cycle.

## Wiring Health Endpoints

For services that don't have a `/health` endpoint yet, the dashboard falls back gracefully to "On Order" status. As you add health endpoints to each service, just update the `health_url` or `status_cmd` in the config.

Minimal health endpoint example (FastAPI):
```python
@app.get("/health")
async def health():
    return {"status": "ok", "service": "my-service"}
```

Or for non-HTTP services, a status script that outputs JSON:
```bash
#!/bin/bash
echo '{"status": "ok", "last_run": "2026-02-13T12:00:00Z"}'
```

## Nginx Proxy Setup

On your home nginx proxy manager, add a proxy host:
- Domain: `valhalla.yourdomain.com`
- Forward to: `<LAN_IP>:8050`
- Enable SSL (Let's Encrypt)
- Optionally add basic auth via Access Lists

## Public Mode

If you intend to expose the dashboard without an auth wall, set these in `.env`:

```bash
PUBLIC_DASHBOARD=true
EXPOSE_INTERNAL_DETAILS=false
ALLOW_MANUAL_CHECKS=false
```

Public mode hides internal host/error details from the UI and API responses
and disables the manual `check-now` action.

## Planned Pages

- [x] System Status (health board)
- [ ] Signal Feed (unified ingestion stream)
- [ ] Portfolio & Positions
- [ ] Monthly Fund Letter generator
- [ ] Cost & Operations
- [ ] Decision Log / Audit Trail
