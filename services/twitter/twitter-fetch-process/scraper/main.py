#!/usr/bin/env python3
"""
Twitter Monitoring System - Main Entry Point

Runs the processing pipeline and HTTP API in a single process:
- Processing loop runs in a background thread
- FastAPI/uvicorn serves the REST API in the main thread
- Health endpoint reflects both database and processing thread status
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from core.pipeline import ProcessingPipeline
from db.connection import init_database
from api.server import app, update_processing_status

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TwitterMonitor:
    """Main monitoring application with unified process architecture."""

    def __init__(
        self,
        process_interval: int = 300,
        batch_size: int = 100,
        api_host: str = "0.0.0.0",
        api_port: int = 8082,
    ):
        """
        Initialize Twitter monitor.

        Args:
            process_interval: Seconds between processing runs
            batch_size: Number of entries to process per batch
            api_host: Host for the API server
            api_port: Port for the API server
        """
        self.process_interval = process_interval
        self.batch_size = batch_size
        self.api_host = api_host
        self.api_port = api_port
        self.running = False
        self.pipeline: Optional[ProcessingPipeline] = None
        self._processing_thread: Optional[threading.Thread] = None

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _interruptible_sleep(self, seconds: int):
        """Sleep that can be interrupted by setting self.running = False."""
        for _ in range(seconds):
            if not self.running:
                break
            time.sleep(1)

    def _processing_loop(self):
        """Background processing loop (runs in a thread)."""
        logger.info("Processing thread started")
        update_processing_status(active=True)
        run_count = 0

        while self.running:
            try:
                run_count += 1
                logger.info(f"[Run #{run_count}] Processing batch...")
                update_processing_status(
                    run_count=run_count,
                    last_run_at=datetime.now().isoformat(),
                    last_error=None,
                )

                stats = self.pipeline.process_batch(limit=self.batch_size)
                logger.info(f"[Run #{run_count}] Batch complete")

                if self.running:
                    logger.info(f"Waiting {self.process_interval}s until next run...")
                    self._interruptible_sleep(self.process_interval)

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                logger.exception(e)
                update_processing_status(last_error=str(e))

                if self.running:
                    logger.info("Waiting 60s before retry...")
                    self._interruptible_sleep(60)

        update_processing_status(active=False)
        logger.info("Processing thread stopped")

    def start(self):
        """Start the monitoring system (processing thread + API server)."""
        import uvicorn

        logger.info("=" * 70)
        logger.info("Twitter Monitoring System Starting")
        logger.info("=" * 70)
        logger.info(f"Process interval: {self.process_interval}s")
        logger.info(f"Batch size: {self.batch_size}")
        logger.info(f"API server: {self.api_host}:{self.api_port}")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Initialize database
        logger.info("Initializing database...")
        try:
            engine = init_database()
            logger.info("Database initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            sys.exit(1)

        # Initialize pipeline
        logger.info("Initializing processing pipeline...")
        try:
            self.pipeline = ProcessingPipeline()
            logger.info("Pipeline initialized")
        except Exception as e:
            logger.error(f"Pipeline initialization failed: {e}")
            sys.exit(1)

        # Start processing loop in background thread
        self.running = True
        self._processing_thread = threading.Thread(
            target=self._processing_loop,
            name="processing-loop",
            daemon=True,
        )
        self._processing_thread.start()

        logger.info("=" * 70)
        logger.info("System running - API server starting")
        logger.info("=" * 70)

        # Run API server in main thread (blocks until shutdown)
        try:
            uvicorn.run(
                app,
                host=self.api_host,
                port=self.api_port,
                log_level="info",
            )
        except Exception as e:
            logger.error(f"API server error: {e}")
        finally:
            self.running = False
            self.shutdown()

    def shutdown(self):
        """Shutdown gracefully."""
        logger.info("=" * 70)
        logger.info("Shutting down...")

        self.running = False

        # Wait for processing thread to finish
        if self._processing_thread and self._processing_thread.is_alive():
            logger.info("Waiting for processing thread to stop...")
            self._processing_thread.join(timeout=10)

        if self.pipeline:
            stats = self.pipeline.get_stats()
            logger.info("Final Statistics:")
            logger.info(f"  Total fetched: {stats['total_fetched']}")
            logger.info(f"  Total stored: {stats['total_stored']}")
            logger.info(f"  Pre-filter skip: {stats['pre_filter_skip']}")
            logger.info(f"  LLM processed: {stats['llm_processed']}")
            logger.info(f"  Errors: {stats['errors']}")

            triage_stats = stats.get('triage_stats', {})
            cost = triage_stats.get('cost_estimate', {})
            if cost:
                logger.info(f"  LLM cost: ${cost.get('total_cost', 0):.4f}")

        logger.info("Shutdown complete")
        logger.info("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Twitter Monitoring System with LLM Triage"
    )
    parser.add_argument(
        '--process-interval',
        type=int,
        default=int(os.getenv('PROCESS_INTERVAL', '300')),
        help="Seconds between processing runs (default: 300)"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=int(os.getenv('BATCH_SIZE', '100')),
        help="Number of entries to process per batch (default: 100)"
    )
    parser.add_argument(
        '--api-port',
        type=int,
        default=int(os.getenv('API_PORT', '8082')),
        help="Port for the REST API server (default: 8082)"
    )
    parser.add_argument(
        '--log-level',
        default=os.getenv('LOG_LEVEL', 'INFO'),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(args.log_level)

    # Validate environment variables
    required_vars = ['MINIFLUX_API_KEY', 'ANTHROPIC_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

    # Start monitor
    monitor = TwitterMonitor(
        process_interval=args.process_interval,
        batch_size=args.batch_size,
        api_port=args.api_port,
    )

    try:
        monitor.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
