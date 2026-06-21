"""Migrate all Miniflux feeds from nitter.net to the local nitter-proxy.

Usage:
    python migrate_feeds.py [--dry-run] [--proxy-url URL]

Reads feeds from Miniflux API, rewrites URLs from any nitter instance
to point at the local proxy, and updates them via PUT.
"""

from __future__ import annotations

import argparse
import re
import sys
from urllib.parse import urlparse

import httpx

MINIFLUX_URL = "http://localhost:8081"
MINIFLUX_API_KEY = ""

NITTER_URL_PATTERN = re.compile(
    r"https?://[^/]*nitter[^/]*/([^/]+)/rss"
    r"|https?://xcancel\.com/([^/]+)/rss"
    r"|https?://lightbrd\.com/([^/]+)/rss"
)


def extract_username(feed_url: str) -> str | None:
    """Extract Twitter username from any known Nitter feed URL."""
    match = NITTER_URL_PATTERN.search(feed_url)
    if match:
        return next(g for g in match.groups() if g is not None)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Miniflux feeds to nitter-proxy")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    parser.add_argument("--proxy-url", default="http://nitter-proxy:8090", help="Proxy base URL")
    parser.add_argument("--miniflux-url", default=MINIFLUX_URL)
    parser.add_argument("--miniflux-key", default=MINIFLUX_API_KEY)
    args = parser.parse_args()

    client = httpx.Client(
        base_url=args.miniflux_url,
        headers={"X-Auth-Token": args.miniflux_key},
        timeout=30,
    )

    r = client.get("/v1/feeds")
    r.raise_for_status()
    feeds = r.json()

    migrated = 0
    skipped = 0
    already_proxied = 0

    for feed in feeds:
        feed_id = feed["id"]
        old_url = feed["feed_url"]

        # Already pointing at proxy
        if args.proxy_url in old_url:
            already_proxied += 1
            continue

        username = extract_username(old_url)
        if not username:
            print(f"  SKIP feed {feed_id}: unrecognized URL {old_url}")
            skipped += 1
            continue

        new_url = f"{args.proxy_url}/{username}/rss"

        if args.dry_run:
            print(f"  [DRY RUN] feed {feed_id}: {old_url} -> {new_url}")
        else:
            r = client.put(f"/v1/feeds/{feed_id}", json={"feed_url": new_url})
            if r.status_code == 204:
                print(f"  UPDATED feed {feed_id} ({username}): {old_url} -> {new_url}")
            else:
                print(f"  ERROR feed {feed_id}: HTTP {r.status_code} {r.text}")
                skipped += 1
                continue

        migrated += 1

    print(f"\nDone: {migrated} migrated, {skipped} skipped, {already_proxied} already proxied")
    if args.dry_run:
        print("(dry run - no changes made)")


if __name__ == "__main__":
    main()
