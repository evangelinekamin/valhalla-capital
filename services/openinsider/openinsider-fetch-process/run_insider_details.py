#!/usr/bin/env python3
"""Scrape individual insider details for tickers (Phase 2)."""

import argparse
import logging
import sys
import time
from decimal import Decimal

from openinsider.config import CONFIG
from openinsider.database import OpenInsiderDB
from openinsider.models import ScrapeLog
from openinsider.scraper import OpenInsiderScraper
from openinsider.utils import setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Scrape OpenInsider individual insider details")

    parser.add_argument(
        "--ticker",
        type=str,
        help="Specific ticker to scrape (e.g., AAPL)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape details for all recent cluster tickers",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit number of tickers to scrape (default: 10)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't save to database)",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be >= 1")

    return args


def scrape_ticker_details(db: OpenInsiderDB, scraper: OpenInsiderScraper, ticker: str, dry_run: bool = False) -> int:
    """
    Scrape individual insider details for a ticker.

    Returns:
        Number of new transactions saved
    """
    try:
        transactions = scraper.scrape_ticker_details(ticker)

        if dry_run:
            print(f"\n{ticker}: Found {len(transactions)} transactions")
            for i, txn in enumerate(transactions[:3], 1):
                print(f"  {i}. {txn['insider_name']} ({txn.get('insider_title', 'N/A')})")
                print(f"     {txn['trade_type']} - {txn['qty']} shares @ ${txn.get('price', 'N/A')}")
            return 0

        new_count = 0
        for txn in transactions:
            is_new = db.save_insider_transaction(txn)
            if is_new:
                new_count += 1

        logger.info(f"{ticker}: Saved {new_count}/{len(transactions)} new transactions")
        return new_count

    except Exception as e:
        logger.error(f"Failed to scrape {ticker}: {e}")
        return 0


def main() -> int:
    """Main execution function."""
    args = parse_args()

    if args.debug:
        CONFIG["logging"]["level"] = "DEBUG"

    setup_logging(CONFIG["logging"])
    logger.info("Starting OpenInsider insider details scraper (Phase 2)")

    if not args.ticker and not args.all:
        print("Error: Must specify --ticker SYMBOL or --all")
        return 1

    db = OpenInsiderDB()

    try:
        start_time = time.time()
        total_new = 0
        tickers_scraped = 0

        with OpenInsiderScraper() as scraper:
            if args.ticker:
                tickers = [args.ticker.upper()]
            else:
                recent = db.get_recent_clusters(limit=args.limit)
                tickers = list(dict.fromkeys(c["ticker"] for c in recent))
                logger.info(
                    f"Found {len(tickers)} unique recent tickers to scrape "
                    f"(from {len(recent)} cluster records)"
                )

            for ticker in tickers:
                new_count = scrape_ticker_details(db, scraper, ticker, dry_run=args.dry_run)
                total_new += new_count
                tickers_scraped += 1

                if tickers_scraped < len(tickers):
                    delay = CONFIG["scraper"]["rate_limit_delay"]
                    logger.debug(f"Rate limiting: waiting {delay}s...")
                    time.sleep(delay)

        duration = Decimal(str(time.time() - start_time))

        if not args.dry_run:
            log = ScrapeLog(
                scrape_type="insider_details",
                records_found=tickers_scraped,
                records_new=total_new,
                duration_seconds=duration,
                status="SUCCESS",
            )
            db.save_scrape_log(log)

        logger.info(
            f"Insider details scrape complete: {tickers_scraped} tickers, {total_new} new transactions ({duration:.2f}s)"
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
                    scrape_type="insider_details",
                    status="FAILED",
                    error_message=str(e),
                )
            )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
