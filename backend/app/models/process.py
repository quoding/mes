from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProcessData(Base):
    """Time-series sensor readings from roll-to-roll process lines.

    Partitioned as a TimescaleDB hypertable on 'time'.
    """

    __tablename__ = "process_data"
    __table_args__ = (
        Index("ix_process_data_line_station_time", "line_id", "station", "time"),
    )

    # TimescaleDB hypertables don't require a surrogate PK; use composite.
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    line_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    station: Mapped[str] = mapped_column(String(32), primary_key=True)
    param: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="")
