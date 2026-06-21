"""PostgreSQL database adapter with TimescaleDB support."""
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from src.models.db.trade import Trade
from src.models.db.risk_check import RiskCheckRecord
from src.models.db.portfolio_snapshot import PortfolioSnapshot
from src.models.db.claude_decision import ClaudeDecision

log = structlog.get_logger()


class DatabaseAdapter:
    """
    Database adapter for PostgreSQL + TimescaleDB.

    Provides high-level methods for querying trades, risk checks,
    and portfolio snapshots.
    """

    def __init__(self, database_url: str):
        """
        Initialize database adapter.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.logger = log.bind(component="database")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def get_today_trade_count(self) -> int:
        """Get number of trades executed today."""
        with self.get_session() as session:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            count = (
                session.query(Trade)
                .filter(Trade.timestamp >= today_start, Trade.status == "FILLED")
                .count()
            )
            self.logger.debug("today_trade_count", count=count)
            return count

    def get_week_trade_count(self) -> int:
        """Get number of trades executed in past 7 days."""
        with self.get_session() as session:
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            count = (
                session.query(Trade).filter(Trade.timestamp >= week_ago, Trade.status == "FILLED").count()
            )
            self.logger.debug("week_trade_count", count=count)
            return count

    def get_daily_pnl_percent(self) -> float:
        """
        Get today's P&L as percentage.

        Returns most recent portfolio snapshot from today.
        """
        with self.get_session() as session:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            # Get most recent snapshot from today
            snapshot = (
                session.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.timestamp >= today_start)
                .order_by(PortfolioSnapshot.timestamp.desc())
                .first()
            )

            pnl_pct = snapshot.daily_pnl_pct if snapshot else 0.0
            self.logger.debug("daily_pnl_percent", pnl_pct=pnl_pct)
            return pnl_pct

    def get_recent_trade(self, ticker: str, minutes: int) -> Optional[dict]:
        """
        Get most recent trade for ticker within timeframe.

        Args:
            ticker: Stock ticker
            minutes: Lookback window in minutes

        Returns:
            Dict with trade details or None
        """
        with self.get_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

            trade = (
                session.query(Trade)
                .filter(
                    Trade.ticker == ticker,
                    Trade.timestamp >= cutoff,
                    Trade.status == "FILLED",
                )
                .order_by(Trade.timestamp.desc())
                .first()
            )

            if trade:
                minutes_ago = int((datetime.now(timezone.utc) - trade.timestamp).total_seconds() / 60)
                return {"action": trade.action, "minutes_ago": minutes_ago}

            return None

    def save_trade(
        self,
        request_id,
        ticker: str,
        action: str,
        quantity: int,
        order_type: str,
        status: str,
        filled_price: Optional[float] = None,
        commission: Optional[float] = None,
        order_id: Optional[int] = None,
        reason: Optional[str] = None,
        kelly_fraction: Optional[float] = None,
        half_kelly_fraction: Optional[float] = None,
        portfolio_value: Optional[float] = None,
        analysis_data: Optional[dict] = None,
        dry_run: bool = False,
    ) -> Trade:
        """
        Save a trade record to database.

        Args:
            Various trade details

        Returns:
            Saved Trade object
        """
        with self.get_session() as session:
            trade = Trade(
                request_id=request_id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type=order_type,
                status=status,
                filled_price=filled_price,
                commission=commission,
                order_id=order_id,
                reason=reason,
                kelly_fraction=kelly_fraction,
                half_kelly_fraction=half_kelly_fraction,
                portfolio_value_at_trade=portfolio_value,
                analysis_data=analysis_data,
                dry_run=dry_run,
            )

            session.add(trade)
            session.commit()
            session.refresh(trade)

            self.logger.info(
                "trade_saved",
                trade_id=trade.id,
                ticker=ticker,
                action=action,
                status=status,
            )

            return trade

    def save_risk_checks(
        self, trade_id: Optional[int], risk_checks: List
    ) -> List[RiskCheckRecord]:
        """
        Save risk check results to database.

        Args:
            trade_id: Associated trade ID (None if trade rejected)
            risk_checks: List of RiskCheck objects

        Returns:
            List of saved RiskCheckRecord objects
        """
        with self.get_session() as session:
            records = []

            for check in risk_checks:
                record = RiskCheckRecord(
                    trade_id=trade_id,
                    check_name=check.name,
                    result=check.status.value.upper(),
                    message=check.message,
                    details=check.details,
                )
                session.add(record)
                records.append(record)

            session.commit()

            self.logger.info(
                "risk_checks_saved", trade_id=trade_id, count=len(records)
            )

            return records

    def save_portfolio_snapshot(self, state) -> PortfolioSnapshot:
        """
        Save portfolio state snapshot to database.

        Args:
            state: PortfolioState object

        Returns:
            Saved PortfolioSnapshot object
        """
        with self.get_session() as session:
            snapshot = PortfolioSnapshot(
                timestamp=state.timestamp,
                total_value=state.total_value,
                cash_balance=state.cash_balance,
                positions=state.positions_dict,
                daily_pnl=state.daily_pnl,
                daily_pnl_pct=state.daily_pnl_pct,
            )

            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)

            self.logger.info(
                "portfolio_snapshot_saved",
                snapshot_id=snapshot.id,
                total_value=state.total_value,
            )

            return snapshot

    def save_claude_decision(
        self,
        ticker: str,
        decision: str,
        confidence: float,
        win_probability: float,
        expected_gain_pct: float,
        expected_loss_pct: float,
        reasoning: str,
        data_sources: Optional[dict] = None,
        trade_id: Optional[int] = None,
    ) -> ClaudeDecision:
        """
        Save Claude's decision and reasoning for future analysis.

        Args:
            Various decision details

        Returns:
            Saved ClaudeDecision object
        """
        with self.get_session() as session:
            decision_record = ClaudeDecision(
                ticker=ticker,
                decision=decision,
                confidence=confidence,
                win_probability=win_probability,
                expected_gain_pct=expected_gain_pct,
                expected_loss_pct=expected_loss_pct,
                reasoning=reasoning,
                data_sources=data_sources,
                trade_id=trade_id,
            )

            session.add(decision_record)
            session.commit()
            session.refresh(decision_record)

            self.logger.info(
                "claude_decision_saved",
                decision_id=decision_record.id,
                ticker=ticker,
                decision=decision,
            )

            return decision_record

    def get_recent_trades(self, limit: int = 10) -> List[Trade]:
        """
        Get most recent trades.

        Args:
            limit: Maximum number of trades to return

        Returns:
            List of Trade objects
        """
        with self.get_session() as session:
            trades = (
                session.query(Trade)
                .order_by(Trade.timestamp.desc())
                .limit(limit)
                .all()
            )
            return trades

    def health_check(self) -> bool:
        """
        Check database connectivity.

        Returns:
            True if database is accessible
        """
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            self.logger.error("database_health_check_failed", error=str(e))
            return False
