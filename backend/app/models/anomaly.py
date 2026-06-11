from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_line_severity", "line_id", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    line_id: Mapped[int] = mapped_column(SmallInteger)
    station: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))  # INFO / WARNING / CRITICAL
    param: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    threshold_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Rolling stats snapshot at detection time (JSON string)
    feature_snapshot: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
