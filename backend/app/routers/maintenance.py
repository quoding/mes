from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ratelimit import check_rate_limit
from app.core.redis import get_redis
from app.models.equipment import Equipment, MaintenanceReport

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

# LLM 호출 비용 통제 — 챗봇(분당 10회)보다 빡빡하게
_GENERATE_RATE_MAX = 3          # IP당 분당 3회
_REPORT_CACHE_MINUTES = 10      # 같은 설비는 10분 내 기존 리포트 재사용


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
    req: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> dict:
    """Trigger a predictive maintenance report for the given equipment.

    내부에서 LLM을 호출하므로 챗봇과 동일한 비용 통제를 적용한다:
    IP rate limit + 최근 리포트 캐싱 (반복 호출이 API 요금으로 새지 않게).
    """
    # 캐시: 같은 설비에 N분 내 생성된 리포트가 있으면 LLM 호출 없이 재사용
    since = datetime.now(timezone.utc) - timedelta(minutes=_REPORT_CACHE_MINUTES)
    cached = await db.execute(
        select(MaintenanceReport)
        .where(MaintenanceReport.equipment_id == equipment_id, MaintenanceReport.generated_at >= since)
        .order_by(MaintenanceReport.generated_at.desc())
        .limit(1)
    )
    if (r := cached.scalar_one_or_none()) is not None:
        return {
            "equipment_id": equipment_id,
            "risk_score": r.risk_score,
            "llm_summary": r.llm_summary,
            "generated_at": r.generated_at.isoformat(),
            "cached": True,
        }

    client_ip = req.client.host if req.client else "unknown"
    await check_rate_limit(redis, f"report:ip:{client_ip}", _GENERATE_RATE_MAX)

    from app.services.predictive import predict_maintenance
    report = await predict_maintenance(equipment_id, db)
    return report
