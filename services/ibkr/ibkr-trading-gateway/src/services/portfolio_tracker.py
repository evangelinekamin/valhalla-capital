"""Portfolio state management and tracking."""
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from src.models.portfolio_state import PortfolioState, Position

log = structlog.get_logger()


class PortfolioTracker:
    """
    Tracks and manages portfolio state.

    Fetches current positions and account values from IBKR,
    maintains cache for performance, and persists snapshots.
    """

    CACHE_TTL_SECONDS = 60  # Cache valid for 1 minute

    def __init__(self, ib_connection, db_adapter):
        """
        Initialize portfolio tracker.

        Args:
            ib_connection: IBKR connection adapter
            db_adapter: Database adapter for persistence
        """
        self.ib = ib_connection
        self.db = db_adapter
        self.logger = log.bind(component="portfolio_tracker")
        self._cache: Optional[PortfolioState] = None
        self._cache_time: Optional[datetime] = None

    def get_current_state(self, force_refresh: bool = False) -> PortfolioState:
        """
        Get current portfolio state from IBKR.

        Args:
            force_refresh: Force refresh bypassing cache

        Returns:
            Current PortfolioState
        """
        if not force_refresh and self._cache_is_valid():
            self.logger.debug("portfolio_state_from_cache")
            return self._cache

        # Fetch from IBKR
        net_liquidation = self.ib.get_account_value("NetLiquidation")
        cash = self.ib.get_account_value("TotalCashValue")

        # Get positions (if available)
        try:
            positions = self._get_positions()
        except Exception as e:
            self.logger.warning("failed_to_fetch_positions", error=str(e))
            positions = []

        # Get daily P&L
        try:
            daily_pnl = self.ib.get_account_value("DailyPnL")
        except Exception as e:
            self.logger.warning("failed_to_fetch_daily_pnl", error=str(e))
            daily_pnl = 0.0

        daily_pnl_pct = daily_pnl / net_liquidation if net_liquidation > 0 else 0.0

        state = PortfolioState(
            timestamp=datetime.now(timezone.utc),
            total_value=net_liquidation,
            cash_balance=cash,
            positions=positions,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
        )

        # Update cache
        self._cache = state
        self._cache_time = datetime.now(timezone.utc)

        self.logger.info(
            "portfolio_state_fetched",
            total_value=net_liquidation,
            cash=cash,
            positions=len(positions),
            daily_pnl_pct=daily_pnl_pct,
        )

        return state

    def update_after_trade(self, trade_result=None) -> PortfolioState:
        """
        Force refresh and persist snapshot after trade execution.

        Args:
            trade_result: Optional trade result for logging

        Returns:
            Updated PortfolioState
        """
        state = self.get_current_state(force_refresh=True)

        # Save snapshot to database
        try:
            self.db.save_portfolio_snapshot(state)
            self.logger.info("portfolio_snapshot_saved", snapshot_id=state.timestamp)
        except Exception as e:
            self.logger.error("failed_to_save_snapshot", error=str(e))

        return state

    def _cache_is_valid(self) -> bool:
        """Check if cached state is still valid."""
        if self._cache is None or self._cache_time is None:
            return False

        age = datetime.now(timezone.utc) - self._cache_time
        return age.total_seconds() < self.CACHE_TTL_SECONDS

    def _get_positions(self) -> list[Position]:
        """
        Fetch current positions from IBKR using portfolio() which includes
        live market prices and unrealized P&L.

        Returns:
            List of Position objects
        """
        # Use ib.portfolio() instead of ib.positions() because portfolio()
        # returns PortfolioItem objects with marketPrice and unrealizedPNL,
        # while positions() returns Position namedtuples without those fields.
        try:
            portfolio_items = self.ib.ib.portfolio()
        except AttributeError:
            # Mock connection doesn't have ib.portfolio()
            return []

        positions = []
        for item in portfolio_items:
            try:
                contract = item.contract
                ticker = contract.symbol
                quantity = int(item.position)

                # Skip if no position
                if quantity == 0:
                    continue

                avg_cost = item.averageCost
                market_price = item.marketPrice

                # Guard against NaN market prices
                if market_price is None or (isinstance(market_price, float) and math.isnan(market_price)):
                    market_price = avg_cost

                market_value = item.marketValue
                if market_value is None or (isinstance(market_value, float) and math.isnan(market_value)):
                    market_value = quantity * market_price

                unrealized_pnl = item.unrealizedPNL
                if unrealized_pnl is None or (isinstance(unrealized_pnl, float) and math.isnan(unrealized_pnl)):
                    unrealized_pnl = 0.0

                unrealized_pnl_pct = (
                    unrealized_pnl / (quantity * avg_cost) if avg_cost > 0 else 0.0
                )

                position = Position(
                    ticker=ticker,
                    quantity=quantity,
                    avg_cost=avg_cost,
                    current_price=market_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                )
                positions.append(position)

            except Exception as e:
                self.logger.warning(
                    "failed_to_parse_position",
                    ticker=getattr(getattr(item, 'contract', None), 'symbol', 'unknown'),
                    error=str(e),
                )
                continue

        return positions
