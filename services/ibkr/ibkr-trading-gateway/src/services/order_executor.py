"""Order execution service for IBKR trades."""
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

log = structlog.get_logger()

# IBKR error code for fractional shares not supported via API
FRACTIONAL_NOT_SUPPORTED_ERROR = 10243


class OrderStatus(Enum):
    """Order execution status."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class ExecutionResult:
    """Result of order execution."""

    ticker: str
    action: str
    quantity: float
    status: OrderStatus
    filled_price: Optional[float] = None
    commission: Optional[float] = None
    order_id: Optional[int] = None
    message: str = ""


def _extract_commission(trade) -> Optional[float]:
    """Extract total commission from ib_insync trade fills.

    Commission lives on fill.commissionReport, not on orderStatus.
    """
    if not trade.fills:
        return None
    total = 0.0
    for fill in trade.fills:
        if fill.commissionReport and fill.commissionReport.commission:
            total += fill.commissionReport.commission
    return total if total > 0 else None


def _was_fractional_rejected(trade) -> bool:
    """Check if the order was rejected because fractional shares aren't supported."""
    for entry in trade.log:
        if entry.errorCode == FRACTIONAL_NOT_SUPPORTED_ERROR:
            return True
    return False


class OrderExecutor:
    """
    Executes orders via IBKR with status tracking.

    Supports market and limit orders with execution confirmation.
    If a fractional order is rejected (error 10243), automatically
    retries with the quantity rounded down to whole shares.
    """

    def __init__(self, ib_connection):
        """
        Initialize order executor.

        Args:
            ib_connection: IBKR connection adapter
        """
        self.ib = ib_connection
        self.logger = log.bind(component="order_executor")

    def execute_market_order(
        self, ticker: str, action: str, quantity: float,
        dry_run: bool = False, current_price: float = 0.0,
    ) -> ExecutionResult:
        """
        Execute a market order.

        Args:
            ticker: Stock ticker
            action: 'BUY' or 'SELL'
            quantity: Number of shares (supports fractional)
            dry_run: If True, simulate a fill without sending to IBKR
            current_price: Current market price (used for dry-run fill simulation)

        Returns:
            ExecutionResult with execution details
        """
        self.logger.info(
            "executing_market_order",
            ticker=ticker,
            action=action,
            quantity=quantity,
            dry_run=dry_run,
        )

        if dry_run:
            return ExecutionResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                status=OrderStatus.FILLED,
                filled_price=current_price if current_price > 0 else None,
                commission=0.0,
                message="Dry run - simulated fill",
            )

        try:
            result = self._try_market_order(ticker, action, quantity)

            # If fractional order was rejected, retry with whole shares
            if result.status == OrderStatus.CANCELLED and quantity != math.floor(quantity):
                whole_qty = math.floor(quantity)
                if whole_qty > 0:
                    self.logger.warning(
                        "fractional_rejected_retrying_whole",
                        ticker=ticker,
                        original_qty=quantity,
                        whole_qty=whole_qty,
                    )
                    result = self._try_market_order(ticker, action, whole_qty)
                else:
                    result.message = "Fractional order rejected and whole quantity would be 0"

            return result

        except Exception as e:
            self.logger.error(
                "market_order_failed", ticker=ticker, error=str(e)
            )
            return ExecutionResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                status=OrderStatus.FAILED,
                message=str(e),
            )

    def _try_market_order(
        self, ticker: str, action: str, quantity: float
    ) -> ExecutionResult:
        """Attempt to place a single market order."""
        trade = self.ib.place_market_order(ticker, action, quantity)

        # Wait briefly for fill
        self.ib.ib.sleep(2)

        status = self._map_status(trade.orderStatus.status)
        commission = _extract_commission(trade)

        result = ExecutionResult(
            ticker=ticker,
            action=action,
            quantity=quantity,
            status=status,
            filled_price=(
                trade.orderStatus.avgFillPrice
                if status == OrderStatus.FILLED
                else None
            ),
            commission=commission,
            order_id=trade.order.orderId,
            message=f"Order {status.value}",
        )

        self.logger.info(
            "market_order_executed",
            ticker=ticker,
            status=status.value,
            quantity=quantity,
            filled_price=result.filled_price,
            commission=result.commission,
            order_id=result.order_id,
        )

        return result

    def execute_limit_order(
        self,
        ticker: str,
        action: str,
        quantity: float,
        limit_price: float,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """
        Execute a limit order.

        Args:
            ticker: Stock ticker
            action: 'BUY' or 'SELL'
            quantity: Number of shares (supports fractional)
            limit_price: Limit price
            dry_run: If True, simulate without executing

        Returns:
            ExecutionResult with execution details
        """
        self.logger.info(
            "executing_limit_order",
            ticker=ticker,
            action=action,
            quantity=quantity,
            limit_price=limit_price,
            dry_run=dry_run,
        )

        if dry_run:
            return ExecutionResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                status=OrderStatus.PENDING,
                message=f"Dry run - limit order @ ${limit_price:.2f}",
            )

        try:
            trade = self.ib.place_limit_order(ticker, action, quantity, limit_price)

            # Brief wait
            self.ib.ib.sleep(1)

            status = self._map_status(trade.orderStatus.status)
            commission = _extract_commission(trade)

            result = ExecutionResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                status=status,
                filled_price=(
                    trade.orderStatus.avgFillPrice
                    if status == OrderStatus.FILLED
                    else limit_price
                ),
                commission=commission,
                order_id=trade.order.orderId,
                message=f"Limit order {status.value} @ ${limit_price:.2f}",
            )

            self.logger.info(
                "limit_order_executed",
                ticker=ticker,
                status=status.value,
                order_id=result.order_id,
            )

            return result

        except Exception as e:
            self.logger.error("limit_order_failed", ticker=ticker, error=str(e))
            return ExecutionResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                status=OrderStatus.FAILED,
                message=str(e),
            )

    def _map_status(self, ib_status: str) -> OrderStatus:
        """
        Map IB status string to OrderStatus enum.

        Args:
            ib_status: Status string from IBKR

        Returns:
            OrderStatus enum value
        """
        mapping = {
            "Filled": OrderStatus.FILLED,
            "Submitted": OrderStatus.SUBMITTED,
            "PendingSubmit": OrderStatus.PENDING,
            "PreSubmitted": OrderStatus.PENDING,
            "Cancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.FAILED,
            "PartiallyFilled": OrderStatus.PARTIAL,
        }

        status = mapping.get(ib_status, OrderStatus.PENDING)
        return status

    def cancel_order(self, order_id: int) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        try:
            return self.ib.cancel_order(order_id)
        except Exception as e:
            self.logger.error("cancel_order_failed", order_id=order_id, error=str(e))
            return False
