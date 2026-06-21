"""SQLAlchemy model for trades table."""
import uuid as uuid_lib
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base


class Trade(Base):
    """Trade execution record."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(UUID(as_uuid=True), default=uuid_lib.uuid4, unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    ticker = Column(String(10), nullable=False, index=True)
    action = Column(String(4), nullable=False)  # BUY or SELL
    quantity = Column(Integer, nullable=False)
    order_type = Column(String(20), nullable=False, default="MARKET")
    status = Column(String(20), nullable=False, index=True)
    filled_price = Column(Float, nullable=True)
    commission = Column(Float, nullable=True)
    order_id = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    kelly_fraction = Column(Float, nullable=True)
    half_kelly_fraction = Column(Float, nullable=True)
    portfolio_value_at_trade = Column(Float, nullable=True)
    analysis_data = Column(JSONB, nullable=True)
    dry_run = Column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, ticker={self.ticker}, "
            f"action={self.action}, quantity={self.quantity}, "
            f"status={self.status})>"
        )
