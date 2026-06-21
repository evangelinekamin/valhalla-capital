#!/usr/bin/env python3
"""
Add Twitter feeds to Miniflux via Nitter.

Usage:
    python add_twitter_feeds.py accounts.txt [options]

Examples:
    python add_twitter_feeds.py accounts.txt --shuffle
    python add_twitter_feeds.py accounts.txt --min-delay 10 --max-delay 30
"""

import argparse
import random
import time
import os
import sys
from pathlib import Path
from typing import List

import requests


class MinifluxClient:
    """Client for Miniflux API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        nitter_url: str = "http://nitter:8080"
    ):
        """
        Initialize Miniflux client.

        Args:
            base_url: Miniflux base URL
            api_key: Miniflux API key
            nitter_url: Nitter instance URL
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.nitter_url = nitter_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'X-Auth-Token': self.api_key,
            'Content-Type': 'application/json'
        })

    def create_feed(self, username: str, category_id: int = 1) -> dict:
        """
        Create a feed for a Twitter user.

        Args:
            username: Twitter username (without @)
            category_id: Miniflux category ID

        Returns:
            Feed creation response
        """
        feed_url = f"{self.nitter_url}/{username}/rss"

        payload = {
            "feed_url": feed_url,
            "category_id": category_id
        }

        response = self.session.post(
            f"{self.base_url}/v1/feeds",
            json=payload
        )

        if response.status_code == 201:
            return response.json()
        elif response.status_code == 409:
            print(f"  ⚠️  Feed already exists: @{username}")
            return None
        else:
            response.raise_for_status()

    def get_categories(self) -> List[dict]:
        """
        Get all categories.

        Returns:
            List of categories
        """
        response = self.session.get(f"{self.base_url}/v1/categories")
        response.raise_for_status()
        return response.json()

    def create_category(self, name: str) -> dict:
        """
        Create a category.

        Args:
            name: Category name

        Returns:
            Category creation response
        """
        payload = {"title": name}
        response = self.session.post(
            f"{self.base_url}/v1/categories",
            json=payload
        )
        response.raise_for_status()
        return response.json()


def read_accounts(file_path: str) -> List[str]:
    """
    Read Twitter accounts from file.

    Args:
        file_path: Path to accounts file (one username per line)

    Returns:
        List of usernames
    """
    accounts = []

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Remove @ if present
            username = line.lstrip('@')

            accounts.append(username)

    return accounts


def add_feeds(
    accounts: List[str],
    miniflux_url: str,
    api_key: str,
    nitter_url: str,
    category_name: str,
    min_delay: int,
    max_delay: int,
    shuffle: bool
):
    """
    Add Twitter feeds to Miniflux.

    Args:
        accounts: List of Twitter usernames
        miniflux_url: Miniflux URL
        api_key: Miniflux API key
        nitter_url: Nitter instance URL
        category_name: Category name for feeds
        min_delay: Minimum delay between requests (seconds)
        max_delay: Maximum delay between requests (seconds)
        shuffle: Whether to shuffle accounts
    """
    client = MinifluxClient(miniflux_url, api_key, nitter_url)

    # Get or create category
    categories = client.get_categories()
    category = next((c for c in categories if c['title'] == category_name), None)

    if not category:
        print(f"Creating category: {category_name}")
        category = client.create_category(category_name)

    category_id = category['id']
    print(f"Using category: {category_name} (ID: {category_id})")

    # Shuffle if requested
    if shuffle:
        print("Shuffling accounts...")
        random.shuffle(accounts)

    # Add feeds
    total = len(accounts)
    added = 0
    skipped = 0

    print(f"\nAdding {total} feeds...")

    for i, username in enumerate(accounts, 1):
        try:
            print(f"[{i}/{total}] Adding @{username}...", end=' ')

            feed = client.create_feed(username, category_id)

            if feed:
                print(f"✓ Added (Feed ID: {feed['id']})")
                added += 1
            else:
                skipped += 1

            # Delay before next request (except for last one)
            if i < total:
                delay = random.uniform(min_delay, max_delay)
                print(f"  Waiting {delay:.1f}s...")
                time.sleep(delay)

        except requests.exceptions.HTTPError as e:
            print(f"✗ Error: {e}")
            skipped += 1

        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            skipped += 1

    print(f"\n{'='*50}")
    print(f"Done! Added: {added}, Skipped: {skipped}, Total: {total}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add Twitter feeds to Miniflux via Nitter"
    )
    parser.add_argument(
        'accounts_file',
        help="Path to accounts file (one username per line)"
    )
    parser.add_argument(
        '--miniflux-url',
        default=os.getenv('MINIFLUX_URL', 'http://localhost:8080'),
        help="Miniflux URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('MINIFLUX_API_KEY'),
        help="Miniflux API key (default: MINIFLUX_API_KEY env var)"
    )
    parser.add_argument(
        '--nitter-url',
        default=os.getenv('NITTER_URL', 'http://nitter:8080'),
        help="Nitter instance URL (default: http://nitter:8080)"
    )
    parser.add_argument(
        '--category',
        default='Twitter',
        help="Category name for feeds (default: Twitter)"
    )
    parser.add_argument(
        '--min-delay',
        type=int,
        default=10,
        help="Minimum delay between requests in seconds (default: 10)"
    )
    parser.add_argument(
        '--max-delay',
        type=int,
        default=30,
        help="Maximum delay between requests in seconds (default: 30)"
    )
    parser.add_argument(
        '--shuffle',
        action='store_true',
        help="Shuffle accounts before adding"
    )

    args = parser.parse_args()

    # Validate API key
    if not args.api_key:
        print("Error: Miniflux API key not provided", file=sys.stderr)
        print("Set MINIFLUX_API_KEY environment variable or use --api-key", file=sys.stderr)
        sys.exit(1)

    # Validate accounts file
    if not Path(args.accounts_file).exists():
        print(f"Error: Accounts file not found: {args.accounts_file}", file=sys.stderr)
        sys.exit(1)

    # Read accounts
    try:
        accounts = read_accounts(args.accounts_file)
        print(f"Loaded {len(accounts)} accounts from {args.accounts_file}")
    except Exception as e:
        print(f"Error reading accounts file: {e}", file=sys.stderr)
        sys.exit(1)

    # Add feeds
    try:
        add_feeds(
            accounts=accounts,
            miniflux_url=args.miniflux_url,
            api_key=args.api_key,
            nitter_url=args.nitter_url,
            category_name=args.category,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            shuffle=args.shuffle
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
