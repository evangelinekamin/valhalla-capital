"""SQLAlchemy model for risk_checks table."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class RiskCheckRecord(Base):
    """Risk validation check record."""

    __tablename__ = "risk_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True, index=True)
    check_name = Column(String(50), nullable=False)
    result = Column(String(20), nullable=False)  # APPROVED, REJECTED, WARNING
    message = Column(Text, nullable=False)
    details = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<RiskCheckRecord(id={self.id}, check_name={self.check_name}, "
            f"result={self.result})>"
        )
