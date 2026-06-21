# orchestrate.py
"""Main pipeline orchestrator for the Substack newsletter processing pipeline."""
import argparse
import logging
import signal
import sys
import time

from config import load_config
from db_schema import init_db
from utils import CostTracker
import discord_notifier

logger = logging.getLogger(__name__)

# --- Graceful shutdown ---
_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    if _shutdown_requested:
        logger.warning("Forced shutdown.")
        sys.exit(1)
    logger.info("Shutdown requested, finishing current batch...")
    _shutdown_requested = True


def should_continue():
    return not _shutdown_requested


def setup_logging(log_level: str, log_file: str = None):
    """Configure root logger with console + optional file handler."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        root.addHandler(fh)


def run_pipeline_fetch(conn, cfg):
    logger.info("Stage 1: Fetching emails...")
    from fetch_emails import run_fetch
    try:
        return run_fetch(conn, cfg.gmail)
    except Exception as e:
        logger.error(f"Error in fetch stage: {e}", exc_info=True)
        discord_notifier.notify_error(e, "fetch", severity="error")
        raise


def run_pipeline_images(conn, cfg):
    logger.info("Stage 2: Downloading images...")
    from process_images import extract_and_download_images
    try:
        extract_and_download_images(conn, image_dir=cfg.images.directory, timeout=cfg.images.download_timeout)

        count = conn.execute(
            "SELECT COUNT(*) FROM images WHERE vision_output IS NULL"
        ).fetchone()[0]
        logger.info(f"Done. {count} images pending vision processing.")
        return count
    except Exception as e:
        logger.error(f"Error in images stage: {e}", exc_info=True)
        discord_notifier.notify_error(e, "images", severity="error")
        raise


def run_pipeline_vision(conn, cfg):
    logger.info("Stage 3: Processing images with vision model...")
    from vision_process import process_unprocessed_images

    model = cfg.model.vision_model or cfg.model.model
    total_tracker = CostTracker(conn)
    batch = 0

    while should_continue():
        remaining = conn.execute(
            "SELECT COUNT(*) FROM images WHERE vision_output IS NULL AND local_path IS NOT NULL"
        ).fetchone()[0]

        if remaining == 0:
            break

        if cfg.pipeline.max_batches and batch >= cfg.pipeline.max_batches:
            logger.info(f"Stopping after {cfg.pipeline.max_batches} batches. {remaining} images remaining.")
            break

        logger.info(f"Processing batch {batch + 1} ({remaining} remaining)...")
        tracker = process_unprocessed_images(
            conn,
            batch_size=cfg.pipeline.batch_size,
            model=model,
            backend=cfg.model.backend,
            **cfg.model.client_kwargs(),
        )
        total_tracker.session_costs.extend(tracker.session_costs)
        batch += 1

        time.sleep(cfg.pipeline.rate_limit_delay)

    logger.info(f"Vision done. Processed {batch} batches. Cost: ${total_tracker.session_total():.4f}")
    return total_tracker


def run_pipeline_extract(conn, cfg):
    logger.info("Stage 4: Extracting structured data...")
    from extract_data import extract_newsletter_content, export_to_json, export_ticker_history

    model = cfg.model.extraction_model or cfg.model.model
    total_tracker = CostTracker(conn)
    batch = 0

    while should_continue():
        remaining = conn.execute('''
            SELECT COUNT(*) FROM emails
            WHERE id NOT IN (SELECT DISTINCT email_id FROM extracted_data WHERE email_id IS NOT NULL)
        ''').fetchone()[0]

        if remaining == 0:
            break

        if cfg.pipeline.max_batches and batch >= cfg.pipeline.max_batches:
            logger.info(f"Stopping after {cfg.pipeline.max_batches} batches. {remaining} emails remaining.")
            break

        logger.info(f"Extracting batch {batch + 1} ({remaining} remaining)...")
        tracker = extract_newsletter_content(
            conn,
            batch_size=cfg.pipeline.batch_size,
            model=model,
            backend=cfg.model.backend,
            **cfg.model.client_kwargs(),
        )
        total_tracker.session_costs.extend(tracker.session_costs)
        batch += 1

        time.sleep(cfg.pipeline.rate_limit_delay)

    logger.info(f"Extraction done. Processed {batch} batches. Cost: ${total_tracker.session_total():.4f}")

    export_to_json(conn, cfg.output.newsletter_data)
    export_ticker_history(conn, cfg.output.ticker_history)

    return total_tracker


def run_stats(conn):
    """Print current pipeline stats."""
    stats = {
        'emails': conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0],
        'images_total': conn.execute("SELECT COUNT(*) FROM images").fetchone()[0],
        'images_processed': conn.execute("SELECT COUNT(*) FROM images WHERE vision_output IS NOT NULL").fetchone()[0],
        'extracted': conn.execute("SELECT COUNT(*) FROM extracted_data").fetchone()[0],
        'tickers': conn.execute("SELECT COUNT(DISTINCT ticker) FROM ticker_updates").fetchone()[0],
        'total_cost': conn.execute("SELECT SUM(cost_usd) FROM api_costs").fetchone()[0] or 0,
    }

    print("\n=== Pipeline Status ===")
    print(f"Emails fetched:      {stats['emails']}")
    print(f"Images downloaded:    {stats['images_total']}")
    print(f"Images processed:     {stats['images_processed']}/{stats['images_total']}")
    print(f"Newsletters parsed:   {stats['extracted']}/{stats['emails']}")
    print(f"Unique tickers:       {stats['tickers']}")
    print(f"Total API cost:       ${stats['total_cost']:.4f}")

    recent = conn.execute('''
        SELECT ticker, action, sentiment, date
        FROM ticker_updates t
        JOIN emails e ON t.email_id = e.id
        ORDER BY e.date DESC
        LIMIT 5
    ''').fetchall()

    if recent:
        print(f"\nRecent ticker updates:")
        for ticker, action, sentiment, date in recent:
            print(f"  {ticker}: {action} ({sentiment}) - {date[:10] if date else 'unknown'}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Newsletter processing pipeline')
    parser.add_argument('--stage', choices=['fetch', 'images', 'vision', 'extract', 'all', 'stats'],
                        default='all', help='Which stage to run')
    parser.add_argument('--batch-size', type=int, default=None, help='Batch size for API calls')
    parser.add_argument('--max-batches', type=int, default=None, help='Max batches per stage')
    parser.add_argument('--model', default=None, help='Model override (applies to all stages)')
    parser.add_argument('--db', default=None, help='Database path override')
    parser.add_argument('--config', default=None, help='Path to config.yaml')

    args = parser.parse_args()

    cfg = load_config(
        config_path=args.config,
        cli_overrides={
            'model': args.model,
            'batch_size': args.batch_size,
            'max_batches': args.max_batches,
            'db': args.db,
        },
    )

    setup_logging(cfg.logging.level, cfg.logging.file)

    # Initialize Discord notifier
    discord_notifier.init_notifier(
        webhook_url=cfg.discord.webhook_url,
        enabled=cfg.discord.enabled
    )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    conn = init_db(cfg.database_path)
    try:
        if args.stage == 'stats':
            run_stats(conn)
            return

        # Send start notification if configured
        if cfg.discord.notify_on_start:
            discord_notifier.notify_message(
                f"Pipeline started (stage: {args.stage})",
                severity="info"
            )

        session_cost = 0

        if args.stage in ('fetch', 'all'):
            run_pipeline_fetch(conn, cfg)

        if args.stage in ('images', 'all') and should_continue():
            run_pipeline_images(conn, cfg)

        if args.stage in ('vision', 'all') and should_continue():
            tracker = run_pipeline_vision(conn, cfg)
            session_cost += tracker.session_total()

        if args.stage in ('extract', 'all') and should_continue():
            tracker = run_pipeline_extract(conn, cfg)
            session_cost += tracker.session_total()

        run_stats(conn)

        if session_cost > 0:
            print(f"Session cost: ${session_cost:.4f}")

        # Send completion notification if configured
        if cfg.discord.notify_on_complete:
            discord_notifier.notify_message(
                f"Pipeline completed successfully (stage: {args.stage}, cost: ${session_cost:.4f})",
                severity="info"
            )

    except Exception as e:
        # Catch any unhandled exceptions and notify
        logger.error(f"Critical pipeline error: {e}", exc_info=True)
        discord_notifier.notify_error(
            e,
            stage=args.stage if 'stage' in args else "unknown",
            severity="critical"
        )
        raise
    finally:
        discord_notifier.flush_suppressed()
        conn.close()
        logger.info("Database connection closed.")


if __name__ == '__main__':
    main()
