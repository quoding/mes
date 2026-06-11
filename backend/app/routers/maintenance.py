from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.equipment import Equipment, MaintenanceReport

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/equipment")
async def list_equipment(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    rows = await db.execute(select(Equipment).order_by(Equipment.line_id, Equipment.station))
    return [
        {
            "id": e.id,
            "name": e.name,
            "line_id": e.line_id,
            "station": e.station,
            "last_maintenance": e.last_maintenance.isoformat() if e.last_maintenance else None,
            "next_maintenance": e.next_maintenance.isoformat() if e.next_maintenance else None,
            "total_hours": e.total_hours,
        }
        for e in rows.scalars()
    ]


@router.get("/reports")
async def list_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
) -> list[dict]:
    rows = await db.execute(
        select(MaintenanceReport).order_by(MaintenanceReport.generated_at.desc()).limit(limit)
    )
    return [
        {
            "id": r.id,
            "generated_at": r.generated_at.isoformat(),
            "equipment_id": r.equipment_id,
            "risk_score": r.risk_score,
            "similar_case_date": r.similar_case_date.isoformat() if r.similar_case_date else None,
            "llm_summary": r.llm_summary,
        }
        for r in rows.scalars()
    ]


@router.post("/reports/generate/{equipment_id}")
async def generate_report(
    equipment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Trigger a predictive maintenance report for the given equipment."""
    from app.services.predictive import predict_maintenance
    report = await predict_maintenance(equipment_id, db)
    return report
