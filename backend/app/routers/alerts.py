from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import FailureAlert
from app.services.signature_engine import signature_engine

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _serialize(row: FailureAlert) -> dict:
    return {
        "id": row.id,
        "signature_id": row.signature_id,
        "line_id": row.line_id,
        "severity": row.severity,
        "confidence": row.confidence,
        "state": row.state,
        "evidence": json.loads(row.evidence) if row.evidence else [],
        "raised_at": row.raised_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "acked_by": row.acked_by,
        "acked_at": row.acked_at.isoformat() if row.acked_at else None,
    }


@router.get("/active")
async def get_active_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    line_id: int | None = Query(None),
) -> list[dict]:
    q = select(FailureAlert).where(FailureAlert.state.in_(["RAISED", "ACTIVE"]))
    if line_id is not None:
        q = q.where(FailureAlert.line_id == line_id)
    q = q.order_by(FailureAlert.raised_at.desc())
    rows = await db.execute(q)
    return [_serialize(r) for r in rows.scalars()]


@router.get("")
async def get_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    line_id: int | None = Query(None),
    state: str | None = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = select(FailureAlert).where(FailureAlert.raised_at >= since)
    if line_id is not None:
        q = q.where(FailureAlert.line_id == line_id)
    if state:
        q = q.where(FailureAlert.state == state.upper())
    q = q.order_by(FailureAlert.raised_at.desc()).limit(limit)
    rows = await db.execute(q)
    return [_serialize(r) for r in rows.scalars()]


@router.post("/{alert_id}/ack")
async def ack_alert(
    alert_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    acked_by: str = Query("operator"),
) -> dict:
    row = await db.get(FailureAlert, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    row.acked_by = acked_by
    row.acked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@router.get("/engine-status")
async def get_engine_status() -> dict:
    return signature_engine.status()


@router.post("/baseline/reset")
async def reset_baseline(line_id: int | None = Query(None)) -> dict:
    await signature_engine.reset_baseline(line_id)
    return {"ok": True, "line_id": line_id}
