"""Main request processor orchestrating the complete trade flow."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import structlog

from src.models.trade_request import TradeRequest
from src.models.trade_result import (
    TradeResult,
    TradeExecution,
    KellyResult,
    RiskCheckResult,
)
from src.services.kelly_calculator import KellyCalculator, KellyInputs
from src.services.risk_validator import RiskValidator, RiskCheckStatus
from src.services.order_executor import OrderExecutor, OrderStatus
from src.services.portfolio_tracker import PortfolioTracker
from src.services.emergency_controller import EmergencyController
from src.adapters.file_io import FileIOAdapter
from src.adapters.database import DatabaseAdapter
from src.adapters.discord_notifier import DiscordNotifier

log = structlog.get_logger()


class RequestProcessor:
    """
    Main orchestrator for trade request processing.

    Coordinates Kelly calculation, risk validation, order execution,
    and result reporting for each trade request.
    """

    def __init__(
        self,
        kelly: KellyCalculator,
        risk: RiskValidator,
        executor: OrderExecutor,
        portfolio: PortfolioTracker,
        emergency: EmergencyController,
        file_io: FileIOAdapter,
        db: DatabaseAdapter,
        discord: DiscordNotifier,
        ib_connection=None,
        dry_run: bool = False,
    ):
        """
        Initialize request processor.

        Args:
            kelly: Kelly calculator service
            risk: Risk validator service
            executor: Order executor service
            portfolio: Portfolio tracker service
            emergency: Emergency controller
            file_io: File I/O adapter
            db: Database adapter
            discord: Discord notifier
            ib_connection: IBKR connection for price lookups
            dry_run: If True, simulates trades without execution
        """
        self.kelly = kelly
        self.risk = risk
        self.executor = executor
        self.portfolio = portfolio
        self.emergency = emergency
        self.file_io = file_io
        self.db = db
        self.discord = discord
        self.ib = ib_connection
        self.dry_run = dry_run
        self.logger = log.bind(component="request_processor")

    def _ensure_connected(self) -> bool:
        """Ensure IBKR connection is alive, reconnect if needed.

        Returns:
            True if connected, False if reconnection failed.
        """
        if self.ib.is_connected():
            return True

        self.logger.warning("ibkr_connection_lost", attempting_reconnect=True)
        if self.ib.reconnect(max_attempts=3):
            self.logger.info("ibkr_reconnected_successfully")
            return True

        self.logger.error("ibkr_reconnect_failed")
        return False

    def process_request_file(self, filepath: Path) -> None:
        """
        Main entry point: process a trade request file.

        Args:
            filepath: Path to trade request JSON file
        """
        # Check panic mode first
        if self.emergency.is_panic_mode():
            self.logger.warning(
                "request_rejected_panic_mode", filepath=str(filepath)
            )
            return

        # Read and validate request
        request = self.file_io.read_request(filepath)
        if request is None:
            self._handle_invalid_request(filepath)
            return

        # Ensure IBKR connection is alive before processing
        if not self._ensure_connected():
            self.logger.error(
                "request_rejected_no_connection",
                request_id=str(request.request_id),
                ticker=request.ticker,
            )
            result = self._create_rejection_result(
                request,
                message="Not connected to IB Gateway and reconnection failed",
            )
            try:
                self.file_io.write_result(result)
            except Exception as e:
                self.logger.error("failed_to_write_result", error=str(e))
            try:
                self.file_io.archive_request(filepath)
            except Exception as e:
                self.logger.error("failed_to_archive_request", error=str(e))
            return

        # Process the request
        result = self._process_request(request)

        # Write result
        try:
            self.file_io.write_result(result)
        except Exception as e:
            self.logger.error(
                "failed_to_write_result",
                request_id=str(request.request_id),
                error=str(e),
            )

        # Archive processed request
        try:
            self.file_io.archive_request(filepath)
        except Exception as e:
            self.logger.error(
                "failed_to_archive_request", filepath=str(filepath), error=str(e)
            )

        # Always update portfolio state after processing (not just on fills)
        try:
            state = self.portfolio.get_current_state(force_refresh=True)
            self.file_io.write_portfolio_state(state)
        except Exception as e:
            self.logger.error("failed_to_update_portfolio_state", error=str(e))

    def _process_request(self, request: TradeRequest) -> TradeResult:
        """
        Process a validated trade request through full pipeline.

        Args:
            request: Validated TradeRequest

        Returns:
            TradeResult with execution details
        """
        self.logger.info(
            "processing_trade_request",
            request_id=str(request.request_id),
            ticker=request.ticker,
            action=request.action,
            overseer_quantity=request.quantity,
        )

        # Get current portfolio value
        portfolio_state = self.portfolio.get_current_state()
        portfolio_value = portfolio_state.total_value

        # Update Kelly calculator with current portfolio value
        self.kelly.update_portfolio_value(portfolio_value)

        # Calculate position size (used as fallback if Overseer didn't send quantity)
        kelly_inputs = KellyInputs(
            win_rate=request.analysis.win_probability,
            avg_win_pct=request.analysis.expected_gain_pct,
            avg_loss_pct=request.analysis.expected_loss_pct,
            confidence=request.analysis.confidence,
        )

        # Fetch current market price
        try:
            current_price = self.ib.get_current_price(request.ticker)
        except Exception as e:
            self.logger.error(
                "price_fetch_failed", ticker=request.ticker, error=str(e),
            )
            return self._create_rejection_result(
                request, message=f"Could not fetch price for {request.ticker}: {e}",
            )

        kelly_result = self.kelly.calculate(kelly_inputs, current_price)

        # Use Overseer's quantity when provided, fall back to Kelly recalculation
        if request.quantity is not None and request.quantity > 0:
            execution_quantity = request.quantity
            self.logger.info(
                "using_overseer_quantity",
                overseer_quantity=request.quantity,
                kelly_quantity=kelly_result.position_size_shares,
            )
        else:
            execution_quantity = kelly_result.position_size_shares
            self.logger.info(
                "using_kelly_quantity",
                kelly_quantity=kelly_result.position_size_shares,
            )

        # Check if position too small or negative edge
        if execution_quantity == 0:
            return self._create_rejection_result(
                request,
                message="Position size too small or negative edge detected",
                kelly=kelly_result,
            )

        # Run risk validation
        risk_checks = self.risk.validate(
            ticker=request.ticker,
            action=request.action,
            quantity=execution_quantity,
            current_price=current_price,
        )

        # Check if approved
        if not self.risk.is_approved(risk_checks):
            failed = [c for c in risk_checks if c.status == RiskCheckStatus.REJECTED]
            self.discord.send_trade_rejected(request.ticker, request.action, failed)

            return self._create_rejection_result(
                request,
                risk_checks=risk_checks,
                kelly=kelly_result,
                message=f"Failed risk checks: {[c.name for c in failed]}",
            )

        # Execute order
        execution = self.executor.execute_market_order(
            ticker=request.ticker,
            action=request.action,
            quantity=execution_quantity,
            dry_run=self.dry_run,
            current_price=current_price,
        )

        # Save to database
        try:
            self._save_trade_to_db(request, execution, kelly_result, risk_checks)
        except Exception as e:
            self.logger.error("failed_to_save_trade", error=str(e))

        # Send Discord notification if executed
        if execution.status == OrderStatus.FILLED:
            self.discord.send_trade_executed(
                ticker=request.ticker,
                action=request.action,
                quantity=execution.quantity,
                price=execution.filled_price or current_price,
                reason=request.reasoning,
            )

        # Create result
        return TradeResult(
            request_id=request.request_id,
            processed_at=datetime.now(timezone.utc),
            approved=execution.status == OrderStatus.FILLED,
            trade_result=TradeExecution(
                ticker=request.ticker,
                action=request.action,
                quantity=execution.quantity,
                status=execution.status.value,
                filled_price=execution.filled_price,
                commission=execution.commission,
                order_id=execution.order_id,
            ),
            risk_checks=[
                RiskCheckResult(
                    name=c.name,
                    passed=c.status != RiskCheckStatus.REJECTED,
                    message=c.message,
                )
                for c in risk_checks
            ],
            kelly_calculation=KellyResult(
                kelly_fraction=kelly_result.kelly_fraction,
                half_kelly_fraction=kelly_result.half_kelly_fraction,
                position_size_usd=kelly_result.position_size_usd,
                position_size_shares=kelly_result.position_size_shares,
            ),
            message=execution.message,
        )

    def _create_rejection_result(
        self,
        request: TradeRequest,
        message: str,
        kelly=None,
        risk_checks: list = None,
    ) -> TradeResult:
        """Create a rejection result."""
        return TradeResult(
            request_id=request.request_id,
            processed_at=datetime.now(timezone.utc),
            approved=False,
            trade_result=None,
            risk_checks=[
                RiskCheckResult(
                    name=c.name,
                    passed=c.status != RiskCheckStatus.REJECTED,
                    message=c.message,
                )
                for c in (risk_checks or [])
            ],
            kelly_calculation=(
                KellyResult(
                    kelly_fraction=kelly.kelly_fraction,
                    half_kelly_fraction=kelly.half_kelly_fraction,
                    position_size_usd=kelly.position_size_usd,
                    position_size_shares=kelly.position_size_shares,
                )
                if kelly
                else None
            ),
            message=message,
        )

    def _handle_invalid_request(self, filepath: Path) -> None:
        """Handle invalid request file."""
        self.logger.error("invalid_request_file", filepath=str(filepath))
        # Could move to error directory instead of archiving
        try:
            self.file_io.archive_request(filepath)
        except Exception as e:
            self.logger.error(
                "failed_to_archive_invalid_request", error=str(e)
            )

    def _save_trade_to_db(
        self, request: TradeRequest, execution, kelly_result, risk_checks
    ) -> None:
        """Save trade and risk checks to database."""
        # Save trade
        trade = self.db.save_trade(
            request_id=request.request_id,
            ticker=request.ticker,
            action=request.action,
            quantity=execution.quantity,
            order_type="MARKET",
            status=execution.status.value,
            filled_price=execution.filled_price,
            commission=execution.commission,
            order_id=execution.order_id,
            reason=request.reasoning,
            kelly_fraction=kelly_result.kelly_fraction,
            half_kelly_fraction=kelly_result.half_kelly_fraction,
            portfolio_value=self.portfolio.get_current_state().total_value,
            analysis_data={
                "win_probability": request.analysis.win_probability,
                "expected_gain_pct": request.analysis.expected_gain_pct,
                "expected_loss_pct": request.analysis.expected_loss_pct,
                "confidence": request.analysis.confidence,
            },
            dry_run=self.dry_run,
        )

        # Save risk checks
        self.db.save_risk_checks(trade.id, risk_checks)

        # Save Claude decision
        self.db.save_claude_decision(
            ticker=request.ticker,
            decision=request.action,
            confidence=request.analysis.confidence,
            win_probability=request.analysis.win_probability,
            expected_gain_pct=request.analysis.expected_gain_pct,
            expected_loss_pct=request.analysis.expected_loss_pct,
            reasoning=request.reasoning,
            trade_id=trade.id,
        )
