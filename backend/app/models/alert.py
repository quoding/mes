from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FailureAlert(Base):
    __tablename__ = "failure_alerts"
    __table_args__ = (
        Index("ix_failure_alert_line_sig", "line_id", "signature_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signature_id: Mapped[str] = mapped_column(String(32))
    line_id: Mapped[int] = mapped_column(SmallInteger)
    severity: Mapped[str] = mapped_column(String(16))  # WARNING | CRITICAL
    confidence: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(16))     # RAISED | ACTIVE | RESOLVED
    evidence: Mapped[str] = mapped_column(Text)         # JSON
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
