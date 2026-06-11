from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.anomaly import AnomalyEvent

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/events")
async def get_anomaly_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    line_id: int | None = Query(None),
    severity: str | None = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = select(AnomalyEvent).where(AnomalyEvent.detected_at >= since)
    if line_id is not None:
        q = q.where(AnomalyEvent.line_id == line_id)
    if severity:
        q = q.where(AnomalyEvent.severity == severity.upper())
    q = q.order_by(AnomalyEvent.detected_at.desc()).limit(limit)
    rows = await db.execute(q)
    return [
        {
            "id": r.id,
            "detected_at": r.detected_at.isoformat(),
            "line_id": r.line_id,
            "station": r.station,
            "severity": r.severity,
            "param": r.param,
            "value": r.value,
            "threshold_low": r.threshold_low,
            "threshold_high": r.threshold_high,
            "pattern_type": r.pattern_type,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
        for r in rows.scalars()
    ]


@router.get("/summary")
async def get_anomaly_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: int = Query(24),
) -> dict:
    """Counts by severity for the KPI dashboard cards."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await db.execute(
        select(AnomalyEvent.severity, AnomalyEvent.line_id)
        .where(AnomalyEvent.detected_at >= since)
    )
    counts: dict[str, int] = {"INFO": 0, "WARNING": 0, "CRITICAL": 0}
    by_line: dict[int, int] = {1: 0, 2: 0}
    for severity, line_id in rows:
        counts[severity] = counts.get(severity, 0) + 1
        by_line[line_id] = by_line.get(line_id, 0) + 1
    return {"by_severity": counts, "by_line": by_line, "hours": hours}
