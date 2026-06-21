"""SQLAlchemy model for portfolio_snapshots table."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class PortfolioSnapshot(Base):
    """Portfolio state snapshot (time-series)."""

    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    cash_balance = Column(Float, nullable=False)
    positions = Column(JSONB, nullable=False, default=dict)
    daily_pnl = Column(Float, nullable=False, default=0.0)
    daily_pnl_pct = Column(Float, nullable=False, default=0.0)

    def __repr__(self) -> str:
        return (
            f"<PortfolioSnapshot(id={self.id}, timestamp={self.timestamp}, "
            f"total_value={self.total_value:.2f})>"
        )
