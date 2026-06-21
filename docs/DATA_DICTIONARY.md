# Valkyrie Overseer / Valhalla Capital — Final Archive

Autonomous AI-driven value-investing experiment. This archive was produced at
controlled shutdown on **2026-06-16** after the portfolio hit its **-10% stop**.

## Outcome (headline numbers)

| Metric | Value |
|---|---|
| Run period | 2026-02-13 (first cycle) → 2026-06-16 (shutdown) |
| Live cutover | 2026-05-01 (IBKR live, account U24244128) |
| Invested capital | $1,000 (started at $500, topped up to $1,000) |
| Final portfolio value | **$902.32** ($547.63 cash + 4 positions ≈ $354.70) |
| Return vs invested | **≈ -9.8% (≈ -$98)** — triggered the -10% stop |
| LLM spend | **$724.51** over 1,700 cycles |
| All-in project cost | ~$1,000 (LLM + hosting + FMP + trading loss) |
| Trades (overseer proposed) | 158 — 77 filled / 71 rejected / 10 stale |
| Trades (executed at broker) | 57 filled (33 sell, 24 buy), 18 failed |

LLM cost by model: deepseek-v3.2 $211.32 (triage) · claude-opus-4-6 $153.23 (16
deep reviews) · qwen-plus $152.10 · claude-sonnet-4-6 $124.23 · claude-haiku-4-5
$56.01 (739 quick checks) · grok-4.1-fast $14.03 · claude-sonnet-4-5 $13.58.

## Architecture (what was running)

- **overseer** — Python agent loop (raw Anthropic SDK + OpenRouter for cheap
  triage), 6 cycle types, 26 tools. Source in `source/services-source.tgz`
  under `services/overseer-app/`.
- **overseer-postgres** — PostgreSQL 15 + pgvector. 15 tables: the agent's
  brain (decisions, learned principles, theses, episodic memory, knowledge base,
  trades, equity curve).
- **IBKR stack** — `ib-gateway` (live) + `trading-service` + `trading-postgres`
  (TimescaleDB): half-Kelly sizing, risk checks, order execution.
- **Data pipelines** — Twitter/Nitter (233k tweets), Substack newsletters,
  OpenInsider, Yellowbrick, news RSS; FMP price/fundamentals cache (MySQL).
- All Docker on a single Hetzner CX33 (Helsinki), migrated from home LXCs
  2026-04-30/05-01.

## Contents

| Dir | What's in it |
|---|---|
| `db/` | Full gzipped SQL dumps: overseer, trading, twitter_data, miniflux, fmp_cache + substack `newsletters.sqlite`. Complete schema+data. |
| `csv/` | Analysis-ready CSV exports of the narrative tables (pgvector embedding columns stripped). **Start here for the writeup.** |
| `logs/` | Per-container logs (timestamped, gzipped). |
| `source/` | `services-source.tgz` — all source, **secrets removed**. `redacted/news_feeds.redacted.json` — monitored feeds with key masked. |
| `state/` | Final `portfolio_state/current.json` + `trade_requests_history.tgz` (110 files). |
| `meta/` | `docker-compose.yml`, `backup.sh`, systemd units, container/image inventory, `config_key_inventory.txt` (key names, values redacted), `secrets_inventory.txt` (filenames only). |

### Best CSVs for analysis
- `overseer_portfolio_daily.csv` — the equity curve (83 trading days).
- `overseer_trades.csv` + `trading_trades.csv` — proposals vs. executions.
- `overseer_decision_journal.csv` — the agent's reasoning (230 entries).
- `overseer_learned_principles.csv` — what it "learned" (559).
- `overseer_thesis_tracker.csv` — per-position investment theses (27).
- `overseer_cycle_logs.csv` — every cycle: model, tokens, cost.
- `overseer_capability_wishes.csv` — capabilities the agent asked for (18).

## Security

This archive contains **no secrets**. All `.env` files were excluded and
`feeds.json` was redacted. `meta/config_key_inventory.txt` lists which config
keys existed (names only). `meta/secrets_inventory.txt` lists secret filenames.
A separate **encrypted** full backup (including secrets + raw data) lives on
Backblaze B2 via restic — final snapshot `de37e3ff` taken 2026-06-16 23:21 UTC.
Restoring it requires the restic password (`/opt/valhalla/secrets/restic-password`,
also in the password manager).

## Shutdown state (2026-06-16)

- **STOPPED**: overseer agent, all data pipelines, overseer DB, FMP, miniflux.
- **LEFT RUNNING**: `ib-gateway`, `trading-service`, `trading-postgres` — so
  account positions/fills can be verified.
- **⚠ Open positions**: at 23:15 UTC the broker still reported **4 positions
  held** (RLI 2, SMMT 10, VISN 6, OBE 3; $902.32 total) despite a manual close —
  likely after-hours sell orders resting for next open. **Verify directly in the
  IBKR app.** Stopping the software does not affect resting orders.
