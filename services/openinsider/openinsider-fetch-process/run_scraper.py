#!/usr/bin/env python3
"""Main entry point for OpenInsider scraper."""

import argparse
import logging
import sys
import time
from decimal import Decimal

from openinsider.config import CONFIG
from openinsider.database import OpenInsiderDB
from openinsider.models import ScrapeLog
from openinsider.scraper import OpenInsiderScraper
from openinsider.utils import send_discord_alert, setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Scrape OpenInsider cluster buys")

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode (scrape but don't save)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (show what would be scraped)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show recent scrape statistics and exit",
    )

    return parser.parse_args()


def show_stats(db: OpenInsiderDB) -> None:
    """Display recent scrape statistics."""
    stats = db.get_scrape_stats(limit=10)

    if not stats:
        print("No scrape history found")
        return

    print("\nRecent Scrape Statistics:")
    print("-" * 80)
    print(f"{'Timestamp':<20} {'Type':<15} {'Found':<8} {'New':<8} {'Updated':<8} {'Status':<10}")
    print("-" * 80)

    for stat in stats:
        print(
            f"{stat['scrape_timestamp'][:19]:<20} "
            f"{stat['scrape_type']:<15} "
            f"{stat['records_found']:<8} "
            f"{stat['records_new']:<8} "
            f"{stat['records_updated']:<8} "
            f"{stat['status']:<10}"
        )

    print("\nRecent Clusters:")
    print("-" * 80)
    clusters = db.get_recent_clusters(limit=5)

    for cluster in clusters:
        value_str = f"${cluster['total_value']:,}" if cluster['total_value'] else "N/A"
        print(
            f"{cluster['ticker']:<8} {cluster['company_name'][:30]:<30} "
            f"Insiders: {cluster['insider_count']:<3} "
            f"Value: {value_str}"
        )


def main() -> int:
    """Main execution function."""
    args = parse_args()

    if args.debug:
        CONFIG["logging"]["level"] = "DEBUG"

    setup_logging(CONFIG["logging"])
    logger.info("Starting OpenInsider scraper")

    try:
        db = OpenInsiderDB()

        if args.stats:
            show_stats(db)
            return 0

        start_time = time.time()
        new_count = 0
        updated_count = 0
        error_message = None

        with OpenInsiderScraper() as scraper:
            clusters = scraper.scrape_cluster_buys()

            if args.dry_run:
                print(f"\nDry run: Found {len(clusters)} cluster buys")
                for i, cluster in enumerate(clusters[:5], 1):
                    print(f"\n{i}. {cluster.ticker} - {cluster.company_name}")
                    print(f"   Insiders: {cluster.insider_count}")
                    print(f"   Trade Date: {cluster.trade_date}")
                    value_str = f"${cluster.total_value:,}" if cluster.total_value else "N/A"
                    print(f"   Value: {value_str}")
                return 0

            if args.test:
                print(f"\nTest mode: Found {len(clusters)} cluster buys (not saving to database)")
                return 0

            for cluster in clusters:
                try:
                    result = db.upsert_cluster_buy(cluster)
                    if result == "inserted":
                        new_count += 1
                    elif result == "updated":
                        updated_count += 1
                except Exception as e:
                    logger.error(f"Failed to save cluster {cluster.ticker}: {e}")
                    continue

        duration = Decimal(str(time.time() - start_time))

        log = ScrapeLog(
            scrape_type="cluster_table",
            records_found=len(clusters),
            records_new=new_count,
            records_updated=updated_count,
            duration_seconds=duration,
            status="SUCCESS",
            error_message=error_message,
        )

        db.save_scrape_log(log)

        logger.info(
            f"Scrape complete: {len(clusters)} found, {new_count} new, {updated_count} updated "
            f"({duration:.2f}s)"
        )

        threshold = CONFIG["discord"]["alert_threshold"]
        if new_count >= threshold:
            send_discord_alert(
                f"🚨 OpenInsider Alert: {new_count} new cluster buys found!\n"
                f"Total: {len(clusters)} | New: {new_count} | Updated: {updated_count}"
            )

        return 0

    except KeyboardInterrupt:
        logger.warning("Scraper interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)

        try:
            db.save_scrape_log(
                ScrapeLog(
                    scrape_type="cluster_table",
                    status="FAILED",
                    error_message=str(e),
                )
            )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
