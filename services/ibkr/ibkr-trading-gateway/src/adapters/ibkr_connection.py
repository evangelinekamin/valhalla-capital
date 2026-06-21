"""Interactive Brokers connection manager with reconnection logic."""
import asyncio
import time
from typing import Optional

import structlog
from ib_insync import IB, Stock, MarketOrder, LimitOrder

log = structlog.get_logger()


class IBKRConnection:
    """
    Manages connection to IB Gateway with automatic reconnection.

    Provides simplified interface for account values, order placement,
    and connection management.
    """

    def __init__(self, host: str, port: int, client_id: int, readonly: bool = False):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.readonly = readonly
        self.ib = IB()
        self._connected = False
        self._loop = None
        self.logger = log.bind(component="ibkr_connection", client_id=client_id)

    def _ensure_loop_for_thread(self):
        """Set the IB event loop on the current thread if missing.

        The file watcher (watchdog) fires callbacks from a background thread
        that has no asyncio event loop. Since the main thread is blocked on
        signal.pause() and not iterating the loop, we can safely reuse it
        from the watcher thread for synchronous ib_insync calls.
        """
        if self._loop is None:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                asyncio.set_event_loop(self._loop)
        except RuntimeError:
            asyncio.set_event_loop(self._loop)

    def connect(self, timeout: int = 30) -> bool:
        if self._connected and self.ib.isConnected():
            self.logger.warning("already_connected")
            return True

        try:
            self.ib.connect(
                self.host,
                self.port,
                clientId=self.client_id,
                readonly=self.readonly,
                timeout=timeout,
            )
            self._connected = True
            self._loop = asyncio.get_event_loop()
            self.logger.info(
                "ibkr_connected", host=self.host, port=self.port, readonly=self.readonly
            )
            return True

        except Exception as e:
            self.logger.error("ibkr_connection_failed", error=str(e))
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._connected:
            try:
                self.ib.disconnect()
                self._connected = False
                self.logger.info("ibkr_disconnected")
            except Exception as e:
                self.logger.error("disconnect_failed", error=str(e))

    def is_connected(self) -> bool:
        return self._connected and self.ib.isConnected()

    def reconnect(self, max_attempts: int = 3) -> bool:
        self.disconnect()

        for attempt in range(max_attempts):
            wait_time = 2**attempt
            self.logger.info(
                "ibkr_reconnect_attempt", attempt=attempt + 1, max_attempts=max_attempts
            )

            if self.connect():
                return True

            if attempt < max_attempts - 1:
                self.logger.info("waiting_before_retry", wait_seconds=wait_time)
                time.sleep(wait_time)

        self.logger.error("ibkr_reconnect_failed", attempts=max_attempts)
        return False

    def get_account_value(self, tag: str = "NetLiquidation") -> float:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        self._ensure_loop_for_thread()

        try:
            account_values = self.ib.accountValues()

            for av in account_values:
                if av.tag == tag:
                    value = float(av.value)
                    self.logger.debug("account_value_fetched", tag=tag, value=value)
                    return value

            raise ValueError(f"Account value tag '{tag}' not found")

        except Exception as e:
            self.logger.error("failed_to_get_account_value", tag=tag, error=str(e))
            raise

    def place_market_order(
        self, ticker: str, action: str, quantity: int
    ) -> Optional[object]:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        if self.readonly:
            raise ValueError("Cannot place orders in readonly mode")

        self._ensure_loop_for_thread()

        try:
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            order = MarketOrder(action, quantity)
            trade = self.ib.placeOrder(contract, order)

            self.logger.info(
                "market_order_placed",
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_id=trade.order.orderId,
            )

            return trade

        except Exception as e:
            self.logger.error(
                "market_order_failed",
                ticker=ticker,
                action=action,
                quantity=quantity,
                error=str(e),
            )
            raise

    def place_limit_order(
        self, ticker: str, action: str, quantity: int, limit_price: float
    ) -> Optional[object]:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        if self.readonly:
            raise ValueError("Cannot place orders in readonly mode")

        self._ensure_loop_for_thread()

        try:
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            order = LimitOrder(action, quantity, limit_price)
            trade = self.ib.placeOrder(contract, order)

            self.logger.info(
                "limit_order_placed",
                ticker=ticker,
                action=action,
                quantity=quantity,
                limit_price=limit_price,
                order_id=trade.order.orderId,
            )

            return trade

        except Exception as e:
            self.logger.error(
                "limit_order_failed",
                ticker=ticker,
                action=action,
                error=str(e),
            )
            raise

    def cancel_order(self, order_id: int) -> bool:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        self._ensure_loop_for_thread()

        try:
            self.ib.cancelOrder(order_id)
            self.logger.info("order_cancelled", order_id=order_id)
            return True

        except Exception as e:
            self.logger.error("order_cancel_failed", order_id=order_id, error=str(e))
            return False

    def cancel_all_orders(self) -> int:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        self._ensure_loop_for_thread()

        try:
            open_orders = self.ib.openOrders()
            for order in open_orders:
                self.ib.cancelOrder(order)

            self.logger.warning("all_orders_cancelled", count=len(open_orders))
            return len(open_orders)

        except Exception as e:
            self.logger.error("cancel_all_orders_failed", error=str(e))
            return 0

    def get_current_price(self, ticker: str) -> float:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        self._ensure_loop_for_thread()

        try:
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            self.ib.reqMarketDataType(4)
            ticker_data = self.ib.reqMktData(contract, snapshot=True)
            self.ib.sleep(2)

            price = ticker_data.marketPrice()
            if price and price > 0 and price != float("inf"):
                self.logger.info("current_price_fetched", ticker=ticker, price=price)
                return float(price)

            if ticker_data.last and ticker_data.last > 0:
                return float(ticker_data.last)

            if ticker_data.close and ticker_data.close > 0:
                return float(ticker_data.close)

            raise ValueError(f"No price data available for {ticker}")

        except ValueError:
            raise
        except Exception as e:
            self.logger.error("price_fetch_failed", ticker=ticker, error=str(e))
            raise ValueError(f"Failed to fetch price for {ticker}: {e}")

    def get_open_orders(self) -> list:
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")

        self._ensure_loop_for_thread()

        return self.ib.openOrders()
