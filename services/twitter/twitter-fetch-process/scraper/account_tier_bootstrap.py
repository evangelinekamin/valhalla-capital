#!/usr/bin/env python3
"""
Account Tier Bootstrap & Auto-Retiering

Two modes:
  1. BOOTSTRAP  - Classify all accounts from scratch using recent tweets from Miniflux.
  2. RETIER     - Re-evaluate tiers based on historical triage logs in the DB.
                  Run weekly/monthly via cron or the weekend orchestrator.

Usage:
    # Initial bootstrap (pulls last ~20 tweets per account from Miniflux)
    python account_tier_bootstrap.py bootstrap

    # Dry-run (prints proposed tiers without writing config)
    python account_tier_bootstrap.py bootstrap --dry-run

    # Re-tier based on accumulated triage data
    python account_tier_bootstrap.py retier

    # Custom thresholds for retiering
    python account_tier_bootstrap.py retier --tier1-threshold 0.50 --tier3-threshold 0.10

Environment variables:
    MINIFLUX_URL, MINIFLUX_API_KEY, ANTHROPIC_API_KEY
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import requests

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from sqlalchemy import create_engine, text
except ImportError:
    create_engine = None

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "account_config.json"
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
TWEETS_PER_ACCOUNT = 20
BATCH_SIZE = 5
API_DELAY = 0.5

# ---------------------------------------------------------------------------
# Miniflux helpers
# ---------------------------------------------------------------------------


def get_miniflux_feeds(base_url: str, api_key: str) -> List[dict]:
    """Fetch all feeds from Miniflux."""
    headers = {"X-Auth-Token": api_key}
    resp = requests.get(f"{base_url}/v1/feeds", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_feed_entries(
    base_url: str, api_key: str, feed_id: int, limit: int = TWEETS_PER_ACCOUNT
) -> List[dict]:
    """Fetch recent entries for a specific feed."""
    headers = {"X-Auth-Token": api_key}
    params = {"limit": limit, "order": "published_at", "direction": "desc"}
    resp = requests.get(
        f"{base_url}/v1/feeds/{feed_id}/entries",
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("entries", [])


def extract_username_from_feed(feed: dict) -> Optional[str]:
    """Extract Twitter username from a Nitter feed URL."""
    url = feed.get("feed_url", "")
    parts = url.rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part == "rss" and i > 0:
            return parts[i - 1]
    site = feed.get("site_url", "")
    if site:
        return site.rstrip("/").split("/")[-1]
    return None


def get_all_accounts_with_tweets(
    base_url: str, api_key: str
) -> Dict[str, List[str]]:
    """Returns {username: [tweet_text, ...]} for all Twitter feeds."""
    feeds = get_miniflux_feeds(base_url, api_key)
    accounts: Dict[str, List[str]] = {}

    for feed in feeds:
        username = extract_username_from_feed(feed)
        if not username:
            print(f"  Warning: Could not extract username from feed: {feed.get('feed_url')}")
            continue

        print(f"  Fetching tweets for @{username} (feed {feed['id']})...")
        try:
            entries = get_feed_entries(base_url, api_key, feed["id"])
            tweets = []
            for entry in entries:
                content = entry.get("content", "")
                text_content = re.sub(r"<[^>]+>", " ", content)
                text_content = re.sub(r"\s+", " ", text_content).strip()
                if text_content:
                    tweets.append(text_content[:500])

            accounts[username] = tweets
            print(f"    -> {len(tweets)} tweets")
        except Exception as e:
            print(f"    Error: {e}")

        time.sleep(0.2)

    return accounts


# ---------------------------------------------------------------------------
# Claude classification
# ---------------------------------------------------------------------------

ACCOUNT_CLASSIFICATION_PROMPT = """You are classifying Twitter accounts for a value-investing trading system's tweet monitoring pipeline. Based on the sample tweets below, categorize each account into exactly ONE tier.

TIER DEFINITIONS:

TIER_1 - High-signal accounts. Consistently post actionable, verifiable market information.
  Typical profiles: institutional analysts, reputable financial journalists,
  well-known fund managers, official company IR accounts.
  Key signal: Most tweets contain concrete data, events, or analysis.

TIER_2 - Standard accounts. Post a mix of useful finance content and general commentary.
  Typical profiles: finance commentators, newsletter writers, experienced retail investors.
  Key signal: Some tweets are valuable, but each tweet needs individual triage.

TIER_3 - Noisy accounts. Post frequently but most content is low-signal for trading.
  Typical profiles: meme-heavy accounts, very high-volume posters where <20% is actionable,
  accounts that mostly retweet or post generic motivational trading content.
  Key signal: You'd have to dig through a lot of noise to find occasional gems.

TIER_FLOW - Flow/data accounts. Post structured market data (options flow, insider trades,
  dark pool prints, unusual volume alerts). Not opinion - just data.
  Key signal: Tweets are structured data dumps, not narrative analysis.

For each account, return your classification and a one-line rationale.

Return ONLY valid JSON in this exact format:
{{
  "classifications": [
    {{"username": "handle1", "tier": "TIER_1", "rationale": "Brief reason"}},
    {{"username": "handle2", "tier": "TIER_2", "rationale": "Brief reason"}}
  ]
}}

ACCOUNTS TO CLASSIFY:

{accounts_block}
"""


def build_accounts_block(accounts_batch: Dict[str, List[str]]) -> str:
    """Format accounts + sample tweets for the classification prompt."""
    blocks = []
    for username, tweets in accounts_batch.items():
        sample = tweets[:TWEETS_PER_ACCOUNT]
        tweet_lines = "\n".join(f"  - {t[:300]}" for t in sample)
        blocks.append(f"@{username} ({len(sample)} recent tweets):\n{tweet_lines}")
    return "\n\n".join(blocks)


def classify_accounts_batch(
    client, accounts_batch: Dict[str, List[str]]
) -> List[dict]:
    """Send a batch of accounts to Claude for tier classification."""
    block = build_accounts_block(accounts_batch)
    prompt = ACCOUNT_CLASSIFICATION_PROMPT.format(accounts_block=block)

    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text_content = response.content[0].text.strip()

    # Strip markdown fences if present
    if "```" in text_content:
        text_content = text_content.split("```")[1]
        if text_content.startswith("json"):
            text_content = text_content[4:]
        text_content = text_content.strip()

    try:
        result = json.loads(text_content)
        return result.get("classifications", [])
    except json.JSONDecodeError as e:
        print(f"  Warning: JSON parse error: {e}")
        print(f"  Raw response: {text_content[:500]}")
        return []


# ---------------------------------------------------------------------------
# Re-tiering from historical triage data
# ---------------------------------------------------------------------------


def get_db_url() -> str:
    """Build database URL from environment variables."""
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "twitter_data")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _extract_handle(stored_username: str) -> str:
    """
    Extract Twitter handle from stored username.

    DB may store usernames in "Display Name / handle" format (from Nitter feed titles)
    or as plain handles. This normalizes to just the handle.
    """
    if ' / ' in stored_username:
        return stored_username.split(' / ')[-1].strip()
    return stored_username.strip()


def retier_from_database(
    db_url: str, days: int = 30, min_tweets: int = 10
) -> Dict[str, dict]:
    """
    Analyze historical triage results to compute signal rates per account.
    Returns {handle: {total, critical, important, routine, noise, signal_rate}}.
    """
    if create_engine is None:
        print("Error: sqlalchemy not installed. Run: pip install sqlalchemy")
        sys.exit(1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT
                    username,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE classification = 'CRITICAL') AS critical,
                    COUNT(*) FILTER (WHERE classification = 'IMPORTANT') AS important,
                    COUNT(*) FILTER (WHERE classification = 'ROUTINE') AS routine,
                    COUNT(*) FILTER (WHERE classification IN ('NOISE', 'SKIP')) AS noise
                FROM tweets
                WHERE classification IS NOT NULL
                  AND processed_at > NOW() - INTERVAL :days_interval
                GROUP BY username
                HAVING COUNT(*) >= :min_tweets
                ORDER BY username
            """),
            {"days_interval": f"{days} days", "min_tweets": min_tweets},
        )

        stats = {}
        for row in result:
            username, total, critical, important, routine, noise = row
            # Normalize "Display Name / handle" to just handle
            handle = _extract_handle(username)
            signal = critical + important
            signal_rate = signal / total if total > 0 else 0
            # If multiple DB usernames map to the same handle, merge stats
            if handle in stats:
                existing = stats[handle]
                existing["total"] += total
                existing["critical"] += critical
                existing["important"] += important
                existing["routine"] += routine
                existing["noise"] += noise
                merged_signal = existing["critical"] + existing["important"]
                existing["signal_rate"] = round(
                    merged_signal / existing["total"] if existing["total"] > 0 else 0, 3
                )
            else:
                stats[handle] = {
                    "total": total,
                    "critical": critical,
                    "important": important,
                    "routine": routine,
                    "noise": noise,
                    "signal_rate": round(signal_rate, 3),
                }

    engine.dispose()
    return stats


def assign_tiers_from_stats(
    stats: Dict[str, dict],
    tier1_threshold: float = 0.40,
    tier3_threshold: float = 0.15,
) -> Dict[str, str]:
    """Assign tiers based on signal rate (fraction of CRITICAL+IMPORTANT tweets)."""
    assignments = {}
    for username, s in stats.items():
        if s["signal_rate"] >= tier1_threshold:
            assignments[username] = "tier_1_high_signal"
        elif s["signal_rate"] < tier3_threshold:
            assignments[username] = "tier_3_noisy"
        else:
            assignments[username] = "tier_2_standard"
    return assignments


# ---------------------------------------------------------------------------
# Config output
# ---------------------------------------------------------------------------


def update_config(
    assignments: Dict[str, str],
    config_path: Path,
    rationales: Optional[Dict[str, str]] = None,
) -> dict:
    """
    Update account_config.json with new tier assignments.
    Preserves manual_overrides, author_context, and flow_data accounts.
    """
    with open(config_path) as f:
        config = json.load(f)

    manual_overrides = {a.lower() for a in config.get("manual_overrides", [])}
    flow_accounts = {
        a.lower()
        for a in config.get("tiers", {}).get("tier_flow_data", {}).get("accounts", [])
    }

    # Build new tier lists, preserving original case from existing config
    existing_accounts = {}
    for tier_key, tier_data in config.get("tiers", {}).items():
        for account in tier_data.get("accounts", []):
            existing_accounts[account.lower()] = account

    new_tiers = {
        "tier_1_high_signal": [],
        "tier_2_standard": [],
        "tier_3_noisy": [],
    }

    for username, tier in assignments.items():
        username_lower = username.lower()

        # Skip manual overrides and flow data accounts
        if username_lower in manual_overrides or username_lower in flow_accounts:
            continue

        # Use original case if available
        display_name = existing_accounts.get(username_lower, username)
        if tier in new_tiers:
            new_tiers[tier].append(display_name)

    # Merge back into config, preserving accounts not in assignments
    # (manual overrides stay in their current tier)
    for tier_key in ["tier_1_high_signal", "tier_2_standard", "tier_3_noisy"]:
        tier_data = config["tiers"][tier_key]
        # Keep manual override accounts in their current tier
        preserved = [
            a for a in tier_data.get("accounts", [])
            if a.lower() in manual_overrides
        ]
        tier_data["accounts"] = preserved + sorted(new_tiers.get(tier_key, []))

    # Add metadata
    config["_last_retier"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_classified": len(assignments),
    }

    return config


def print_summary(assignments: Dict[str, str], stats: Optional[Dict[str, dict]] = None):
    """Print a human-readable summary of tier assignments."""
    tier_groups = {}
    for username, tier in assignments.items():
        tier_groups.setdefault(tier, []).append(username)

    print("\n" + "=" * 60)
    print("  ACCOUNT TIER ASSIGNMENTS")
    print("=" * 60)

    for tier in ["tier_1_high_signal", "tier_2_standard", "tier_3_noisy", "tier_flow_data"]:
        accounts = sorted(tier_groups.get(tier, []))
        print(f"\n{tier.upper()} ({len(accounts)} accounts):")
        for acc in accounts:
            extra = ""
            if stats and acc in stats:
                s = stats[acc]
                extra = f" (signal={s['signal_rate']*100:.0f}%, {s['total']} tweets)"
            print(f"  @{acc}{extra}")

    print(f"\n{'=' * 60}")
    print(f"Total: {len(assignments)} accounts classified")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_bootstrap(args: argparse.Namespace) -> None:
    """Bootstrap tier assignments from Miniflux tweet data."""
    miniflux_url = args.miniflux_url or os.getenv("MINIFLUX_URL", "http://localhost:8081")
    miniflux_key = args.miniflux_api_key or os.getenv("MINIFLUX_API_KEY", "")
    api_key = args.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")

    if not miniflux_key:
        print("Error: MINIFLUX_API_KEY not set. Use --miniflux-api-key or env var.")
        sys.exit(1)
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set. Use --anthropic-api-key or env var.")
        sys.exit(1)
    if anthropic is None:
        print("Error: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    # Step 1: Pull tweets from Miniflux
    print("Step 1: Fetching recent tweets from Miniflux...")
    accounts = get_all_accounts_with_tweets(miniflux_url, miniflux_key)
    print(f"  Found {len(accounts)} accounts with tweets.\n")

    if not accounts:
        print("No accounts found. Check your Miniflux connection and feeds.")
        sys.exit(1)

    # Step 2: Classify in batches
    print("Step 2: Classifying accounts with Claude...")
    client = anthropic.Anthropic(api_key=api_key)

    all_classifications = []
    usernames = list(accounts.keys())

    for i in range(0, len(usernames), BATCH_SIZE):
        batch_usernames = usernames[i : i + BATCH_SIZE]
        batch = {u: accounts[u] for u in batch_usernames}
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(usernames) + BATCH_SIZE - 1) // BATCH_SIZE

        print(
            f"  Batch {batch_num}/{total_batches}: "
            f"{', '.join('@' + u for u in batch_usernames)}"
        )

        results = classify_accounts_batch(client, batch)
        all_classifications.extend(results)

        if i + BATCH_SIZE < len(usernames):
            time.sleep(API_DELAY)

    # Step 3: Build assignments
    tier_map = {
        "TIER_1": "tier_1_high_signal",
        "TIER_2": "tier_2_standard",
        "TIER_3": "tier_3_noisy",
        "TIER_FLOW": "tier_flow_data",
    }
    assignments = {}
    for item in all_classifications:
        username = item.get("username", "").lstrip("@")
        tier = tier_map.get(item.get("tier", "TIER_2"), "tier_2_standard")
        assignments[username] = tier

    print_summary(assignments)

    # Step 4: Write config
    output_path = Path(args.output or DEFAULT_CONFIG_PATH)
    if args.dry_run:
        print(f"\n[DRY RUN] Would write config to {output_path}")
    else:
        config = update_config(assignments, output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\nTier config written to {output_path}")

    # Cost estimate
    total_tweets = sum(len(t) for t in accounts.values())
    est_input_tokens = total_tweets * 80
    est_cost = (est_input_tokens / 1_000_000) * 0.80
    print(
        f"\nEstimated API cost: ~${est_cost:.2f} "
        f"({total_tweets} tweets, ~{est_input_tokens:,} input tokens)"
    )


def cmd_retier(args: argparse.Namespace) -> None:
    """Re-tier accounts based on historical triage data in the database."""
    db_url = args.db_url or get_db_url()

    print("Step 1: Analyzing historical triage data...")
    stats = retier_from_database(db_url, days=args.days, min_tweets=args.min_tweets)
    print(f"  Found data for {len(stats)} accounts.\n")

    if not stats:
        print("No triage data found. Run bootstrap first, or check your DB connection.")
        sys.exit(1)

    # Print per-account stats
    print(
        f"{'Account':<25} {'Total':>6} {'Crit':>5} {'Imp':>5} "
        f"{'Rout':>5} {'Noise':>6} {'Signal%':>8}"
    )
    print("-" * 70)
    for username, s in sorted(stats.items(), key=lambda x: -x[1]["signal_rate"]):
        print(
            f"@{username:<24} {s['total']:>6} {s['critical']:>5} "
            f"{s['important']:>5} {s['routine']:>5} {s['noise']:>6} "
            f"{s['signal_rate']*100:>7.1f}%"
        )

    # Assign tiers
    assignments = assign_tiers_from_stats(
        stats,
        tier1_threshold=args.tier1_threshold,
        tier3_threshold=args.tier3_threshold,
    )

    print_summary(assignments, stats)

    # Write config
    output_path = Path(args.output or DEFAULT_CONFIG_PATH)
    if args.dry_run:
        print(f"\n[DRY RUN] Would write config to {output_path}")
    else:
        config = update_config(assignments, output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\nUpdated tier config written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap and maintain Twitter account tier assignments"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- bootstrap subcommand ---
    bp = subparsers.add_parser(
        "bootstrap", help="Initial classification from Miniflux tweets"
    )
    bp.add_argument("--miniflux-url", help="Miniflux URL")
    bp.add_argument("--miniflux-api-key", help="Miniflux API key")
    bp.add_argument("--anthropic-api-key", help="Anthropic API key")
    bp.add_argument(
        "--output", "-o", help=f"Output path (default: {DEFAULT_CONFIG_PATH})"
    )
    bp.add_argument(
        "--dry-run", action="store_true", help="Print results without writing config"
    )
    bp.set_defaults(func=cmd_bootstrap)

    # --- retier subcommand ---
    rp = subparsers.add_parser(
        "retier", help="Re-tier based on historical triage data"
    )
    rp.add_argument("--db-url", help="PostgreSQL connection URL")
    rp.add_argument(
        "--output", "-o", help=f"Output path (default: {DEFAULT_CONFIG_PATH})"
    )
    rp.add_argument(
        "--dry-run", action="store_true", help="Print results without writing config"
    )
    rp.add_argument("--days", type=int, default=30, help="Days of history to analyze")
    rp.add_argument(
        "--min-tweets", type=int, default=10, help="Minimum tweets to evaluate account"
    )
    rp.add_argument(
        "--tier1-threshold",
        type=float,
        default=0.40,
        help="Signal rate threshold for Tier 1 (default: 0.40 = 40%%)",
    )
    rp.add_argument(
        "--tier3-threshold",
        type=float,
        default=0.15,
        help="Signal rate threshold below which -> Tier 3 (default: 0.15 = 15%%)",
    )
    rp.set_defaults(func=cmd_retier)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
