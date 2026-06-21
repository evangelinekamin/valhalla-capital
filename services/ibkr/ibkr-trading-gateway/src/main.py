"""Main application entry point for IBKR Trading Gateway."""
import signal
import sys
import threading
from pathlib import Path

import structlog

from config.settings import Settings
from src.utils.logging import setup_logging
from src.adapters.ibkr_connection import IBKRConnection
from src.adapters.database import DatabaseAdapter
from src.adapters.discord_notifier import DiscordNotifier
from src.adapters.file_io import FileIOAdapter
from src.services.kelly_calculator import KellyCalculator
from src.services.risk_validator import RiskValidator
from src.services.order_executor import OrderExecutor
from src.services.portfolio_tracker import PortfolioTracker
from src.services.emergency_controller import EmergencyController
from src.services.request_processor import RequestProcessor
from src.services.file_watcher import FileWatcher

log = structlog.get_logger()

PORTFOLIO_WRITE_INTERVAL_SECONDS = 300  # 5 minutes


class TradingGateway:
    """Main trading gateway application."""

    def __init__(self):
        """Initialize trading gateway."""
        self.settings = Settings()
        self._running = False
        self.watcher = None
        self._portfolio_timer = None

    def setup(self) -> None:
        """Set up all services and connections."""
        # Setup logging
        setup_logging(log_level="INFO")

        log.info(
            "starting_trading_gateway",
            trading_mode=self.settings.trading_mode,
            dry_run=self.settings.dry_run_mode,
        )

        # Initialize database
        self.db = DatabaseAdapter(self.settings.database_url)

        # Test database connection
        if not self.db.health_check():
            log.error("database_connection_failed")
            sys.exit(1)

        # Initialize IBKR connection
        self.ib = IBKRConnection(
            host=self.settings.ibkr_host,
            port=self.settings.ibkr_port,
            client_id=self.settings.ibkr_client_id,
            readonly=False,
        )

        # Connect to IBKR
        if not self.ib.connect():
            log.error("failed_to_connect_to_ibkr")
            sys.exit(1)

        # Initialize Discord notifier
        self.discord = DiscordNotifier(
            webhook_url=self.settings.discord_webhook_url, enabled=True
        )

        # Test Discord connection
        # self.discord.test_connection()

        # Initialize File I/O
        self.file_io = FileIOAdapter(
            requests_path=self.settings.trade_requests_path,
            results_path=self.settings.trade_results_path,
            portfolio_path=self.settings.portfolio_state_path,
        )

        # Initialize services
        self.portfolio = PortfolioTracker(self.ib, self.db)

        # Get initial portfolio value and write state file
        try:
            portfolio_state = self.portfolio.get_current_state()
            portfolio_value = portfolio_state.total_value
            self.file_io.write_portfolio_state(portfolio_state)
            log.info("initial_portfolio_value", value=portfolio_value)
        except Exception as e:
            log.warning(
                "failed_to_fetch_portfolio_value",
                error=str(e),
                using_default=self.settings.initial_portfolio_value,
            )
            portfolio_value = self.settings.initial_portfolio_value

        # Emergency controller
        panic_state_file = Path("/app/data/panic_state.json")
        self.emergency = EmergencyController(
            ib_connection=self.ib,
            discord_notifier=self.discord,
            state_file=panic_state_file,
        )

        # Check if starting in panic mode
        if self.emergency.is_panic_mode():
            log.critical("STARTING_IN_PANIC_MODE")
            self.discord.send_error_alert(
                error_type="Panic Mode Active",
                error_message="System started with panic mode active from previous session. "
                "Manual reset required.",
            )

        # Risk validator
        self.risk = RiskValidator(db=self.db, ib=self.ib, settings=self.settings)

        # Kelly calculator
        self.kelly = KellyCalculator(
            portfolio_value=portfolio_value, settings=self.settings
        )

        # Order executor
        self.executor = OrderExecutor(ib_connection=self.ib)

        # Request processor
        self.processor = RequestProcessor(
            kelly=self.kelly,
            risk=self.risk,
            executor=self.executor,
            portfolio=self.portfolio,
            emergency=self.emergency,
            file_io=self.file_io,
            db=self.db,
            discord=self.discord,
            ib_connection=self.ib,
            dry_run=self.settings.dry_run_mode,
        )

        # File watcher
        self.watcher = FileWatcher(
            watch_path=self.settings.trade_requests_path,
            callback=self.processor.process_request_file,
        )

        log.info("trading_gateway_initialized")

    def _start_portfolio_writer(self) -> None:
        """Start background thread that writes portfolio state periodically."""
        def write_loop():
            if not self._running:
                return
            try:
                state = self.portfolio.get_current_state(force_refresh=True)
                self.file_io.write_portfolio_state(state)
                log.info(
                    "periodic_portfolio_state_written",
                    total_value=state.total_value,
                    cash=state.cash_balance,
                    positions=len(state.positions),
                )
            except Exception as e:
                log.warning("periodic_portfolio_write_failed", error=str(e))
            if self._running:
                self._portfolio_timer = threading.Timer(
                    PORTFOLIO_WRITE_INTERVAL_SECONDS, write_loop
                )
                self._portfolio_timer.daemon = True
                self._portfolio_timer.start()

        self._portfolio_timer = threading.Timer(
            PORTFOLIO_WRITE_INTERVAL_SECONDS, write_loop
        )
        self._portfolio_timer.daemon = True
        self._portfolio_timer.start()
        log.info(
            "portfolio_writer_started",
            interval_seconds=PORTFOLIO_WRITE_INTERVAL_SECONDS,
        )

    def run(self) -> None:
        """Start the trading gateway."""
        self._running = True

        # Process any existing requests
        log.info("processing_existing_requests")
        count = self.watcher.process_existing()
        log.info("existing_requests_processed", count=count)

        # Start watching for new requests
        self.watcher.start()

        # Start periodic portfolio state writer
        self._start_portfolio_writer()

        log.info("trading_gateway_running")

        # Keep running until shutdown
        while self._running:
            try:
                signal.pause()
            except KeyboardInterrupt:
                break

    def shutdown(self) -> None:
        """Shutdown the trading gateway gracefully."""
        log.info("shutting_down_trading_gateway")
        self._running = False

        # Stop portfolio writer
        if self._portfolio_timer is not None:
            self._portfolio_timer.cancel()

        # Stop file watcher
        if self.watcher:
            self.watcher.stop()

        # Disconnect from IBKR
        if self.ib:
            self.ib.disconnect()

        # Close Discord client
        if self.discord:
            self.discord.close()

        log.info("trading_gateway_stopped")


def main():
    """Main entry point."""
    gateway = TradingGateway()

    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        log.info("shutdown_signal_received", signal=signum)
        gateway.shutdown()
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        gateway.setup()
        gateway.run()
    except Exception as e:
        log.critical("fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
