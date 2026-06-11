from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    line_id: Mapped[int] = mapped_column(SmallInteger)
    station: Mapped[str] = mapped_column(String(32))
    install_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_maintenance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_maintenance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_hours: Mapped[float] = mapped_column(Float, default=0.0)
    # Threshold config JSON: {"param": {"low": x, "high": y}, ...}
    thresholds: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaintenanceReport(Base):
    __tablename__ = "maintenance_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    equipment_id: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[float] = mapped_column(Float)  # 0–100
    similar_case_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
