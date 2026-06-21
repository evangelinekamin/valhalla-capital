#!/usr/bin/env python3
"""
Yellowbrick Scraper - Main Entry Point

Usage:
    python run_scraper.py                    # Run all feeds
    python run_scraper.py --feed big_money   # Run specific feed
    python run_scraper.py --feed elite       # Run specific feed
    python run_scraper.py --test             # Test authentication
    python run_scraper.py --dry-run          # Dry run (no DB writes)
"""

import sys
import argparse
import logging
import time
from contextlib import nullcontext
from datetime import datetime

from yellowbrick import YellowbrickAuth, YellowbrickDB, YellowbrickScraper
from yellowbrick.config import CONFIG
from yellowbrick.models import ScrapeLog, ScrapeStatus
from yellowbrick.utils import send_discord_alert, setup_logging

def main():
    parser = argparse.ArgumentParser(description='Yellowbrick Scraper')
    parser.add_argument(
        '--feed',
        choices=['big_money', 'elite', 'all'],
        default='all',
        help='Which feed to scrape'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test authentication only'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without writing to database'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = 'DEBUG' if args.debug else CONFIG['logging']['level']
    setup_logging(log_level, CONFIG['logging']['file'])
    logger = logging.getLogger(__name__)

    logger.info("="*70)
    logger.info("Yellowbrick Scraper Starting")
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Feed: {args.feed}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("="*70)

    try:
        # Initialize authentication
        auth = YellowbrickAuth(CONFIG['auth']['cookie_file'])

        if args.test:
            # Test mode - just verify cookies exist and are valid
            if auth.validate_cookies():
                logger.info("Authentication cookies validated successfully")
                send_discord_alert(
                    "Yellowbrick auth test passed",
                    CONFIG['discord']['webhook_url']
                )
                return 0
            else:
                logger.error("Authentication validation failed")
                logger.error("Please export cookies from browser to: %s", CONFIG['auth']['cookie_file'])
                send_discord_alert(
                    "Yellowbrick auth test failed",
                    CONFIG['discord']['webhook_url']
                )
                return 1

        # Initialize database (unless dry run)
        db_instance = YellowbrickDB(CONFIG['database']['path']) if not args.dry_run else None
        db_cm = db_instance if db_instance is not None else nullcontext(None)

        # Initialize scraper
        scraper = YellowbrickScraper(
            auth,
            headless=CONFIG['playwright']['headless'],
            timeout=CONFIG['playwright']['timeout']
        )

        # Determine which feeds to scrape
        if args.feed == 'all':
            feeds_to_scrape = ['big_money', 'elite']
        else:
            feeds_to_scrape = [args.feed]

        results = {}

        with db_cm as db, scraper:
            for feed_name in feeds_to_scrape:
                feed_config = CONFIG['feeds'][feed_name]
                start_time = time.time()

                logger.info(f"Scraping {feed_name} feed...")

                try:
                    pitches = scraper.scrape_feed(feed_config['url'], feed_name)
                    duration = time.time() - start_time

                    pitches_new = 0
                    pitches_updated = 0

                    if db:
                        for pitch in pitches:
                            was_new = db.upsert_pitch(pitch)
                            if was_new:
                                pitches_new += 1
                            else:
                                pitches_updated += 1

                    # Create scrape log
                    scrape_log = ScrapeLog(
                        feed_type=feed_name,
                        pitches_found=len(pitches),
                        pitches_new=pitches_new,
                        pitches_updated=pitches_updated,
                        duration_seconds=duration,
                        status=ScrapeStatus.SUCCESS.value,
                        error_message=None
                    )

                    if db:
                        db.save_scrape_log(scrape_log)

                    results[feed_name] = scrape_log

                    logger.info(f"{feed_name}: SUCCESS")
                    logger.info(f"  Found: {len(pitches)}")
                    logger.info(f"  New: {pitches_new}")
                    logger.info(f"  Updated: {pitches_updated}")
                    logger.info(f"  Duration: {duration:.2f}s")

                except Exception as e:
                    duration = time.time() - start_time
                    error_msg = str(e)

                    scrape_log = ScrapeLog(
                        feed_type=feed_name,
                        pitches_found=0,
                        pitches_new=0,
                        pitches_updated=0,
                        duration_seconds=duration,
                        status=ScrapeStatus.FAILED.value,
                        error_message=error_msg
                    )

                    if db:
                        db.save_scrape_log(scrape_log)

                    results[feed_name] = scrape_log

                    logger.error(f"{feed_name}: FAILED")
                    logger.error(f"  Error: {error_msg}")

                # Rate limiting between feeds
                if len(feeds_to_scrape) > 1 and feed_name != feeds_to_scrape[-1]:
                    delay = CONFIG['rate_limiting']['delay_between_feeds']
                    logger.info(f"Waiting {delay}s before next feed...")
                    time.sleep(delay)

        # Report final results
        logger.info("="*70)
        logger.info("Scraping Complete")
        logger.info("="*70)

        total_found = sum(log.pitches_found for log in results.values())
        total_new = sum(log.pitches_new for log in results.values())
        total_updated = sum(log.pitches_updated for log in results.values())
        failed_feeds = [name for name, log in results.items() if log.status == ScrapeStatus.FAILED.value]

        # Alert on zero pitches (most dangerous silent failure mode)
        if total_found == 0 and not failed_feeds:
            logger.warning("All feeds returned 0 pitches - possible site change or auth issue")
            send_discord_alert(
                "Yellowbrick WARNING: All feeds returned 0 pitches. "
                "Possible site structure change or expired cookies.",
                CONFIG['discord']['webhook_url']
            )

        # Send Discord notifications
        if total_new > 0:
            send_discord_alert(
                f"Yellowbrick: {total_new} new pitches, {total_updated} updated",
                CONFIG['discord']['webhook_url']
            )

        if failed_feeds:
            send_discord_alert(
                f"Yellowbrick scrape failed for: {', '.join(failed_feeds)}",
                CONFIG['discord']['webhook_url']
            )

        return 0 if not failed_feeds else 1

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        send_discord_alert(
            f"Yellowbrick scraper crashed: {str(e)}",
            CONFIG['discord']['webhook_url']
        )
        return 1

if __name__ == '__main__':
    sys.exit(main())
