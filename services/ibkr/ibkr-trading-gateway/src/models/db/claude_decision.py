"""SQLAlchemy model for claude_decisions table (for future analysis)."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class ClaudeDecision(Base):
    """Claude's trading decision and reasoning (for analysis and improvement)."""

    __tablename__ = "claude_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    ticker = Column(String(10), nullable=True, index=True)
    decision = Column(String(20), nullable=False)  # BUY, SELL, HOLD
    confidence = Column(Float, nullable=False)
    win_probability = Column(Float, nullable=False)
    expected_gain_pct = Column(Float, nullable=False)
    expected_loss_pct = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=False)
    data_sources = Column(JSONB, nullable=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True, index=True)

    def __repr__(self) -> str:
        return (
            f"<ClaudeDecision(id={self.id}, ticker={self.ticker}, "
            f"decision={self.decision}, confidence={self.confidence:.2f})>"
        )
