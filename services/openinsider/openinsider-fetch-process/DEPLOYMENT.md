# Deployment & Operations Guide (Debian LXC)

This runbook is tuned for deployment in your `data-collection` LXC and assumes neighboring LXCs provide other services:

- `data-collection` — `<LAN_IP>` (this scraper)
- `fmp` — `<LAN_IP>`
- `trading` — `<LAN_IP>`
- `overseer` — `<LAN_IP>`
- `dashboard` — `<LAN_IP>`

## 1) Pre-deployment checks

Run from the repo root:

```bash
python3 -m pip install -r requirements.txt
pytest -q
python run_scraper.py --dry-run
python run_insider_details.py --all --limit 3 --dry-run
```

## 2) Network sanity checks (optional but recommended)

From `data-collection`, verify intra-LXC reachability:

```bash
ping -c 2 <LAN_IP>
ping -c 2 <LAN_IP>
ping -c 2 <LAN_IP>
ping -c 2 <LAN_IP>
```

## 3) Install as systemd services

```bash
sudo ./deploy/install.sh
```

Then confirm timers and service health:

```bash
systemctl list-timers 'openinsider-*'
systemctl status openinsider-cluster.timer openinsider-details.timer --no-pager
systemctl start openinsider-cluster.service
journalctl -u openinsider-cluster.service -n 50 --no-pager
```

## 4) Rollback strategy

- Disable timers: `sudo systemctl disable --now openinsider-cluster.timer openinsider-details.timer`
- Restore prior app directory backup if maintained.
- Re-enable once fixed.

## 5) Operational notes

- Phase 2 rate limiting is intentionally centralized in `run_insider_details.py` so scheduling and throughput are easier to reason about.
- `.env` should be managed as host-controlled secret/config material in production.
