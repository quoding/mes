"""Process data REST API — latest values + historical queries."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.process import ProcessData
from app.services.simulator import STATION_PARAMS, AnomalyType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


@router.get("/latest")
async def get_latest(
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> dict:
    """Return the most recent value for every parameter on every line."""
    raw = await redis.hgetall("process:latest")
    result: dict[str, dict] = {}
    for hkey, val in raw.items():
        # hkey format: line:{line_id}:{station}:{param}
        result[hkey] = json.loads(val)
    return result


@router.get("/history")
async def get_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    line_id: int = Query(1),
    station: str = Query("coating"),
    param: str = Query("tension_supply"),
    minutes: int = Query(30, ge=1, le=1440),
) -> list[dict]:
    """Return time-series history for a specific parameter."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = await db.execute(
        select(ProcessData)
        .where(
            ProcessData.line_id == line_id,
            ProcessData.station == station,
            ProcessData.param == param,
            ProcessData.time >= since,
        )
        .order_by(ProcessData.time)
    )
    return [
        {"time": r.time.isoformat(), "value": r.value, "unit": r.unit}
        for r in rows.scalars()
    ]


@router.get("/thresholds")
async def get_thresholds() -> dict:
    """Return normal operating ranges for all parameters."""
    result: dict[str, dict[str, dict[str, float]]] = {}
    for station, params in STATION_PARAMS.items():
        result[station] = {}
        for p in params:
            result[station][p.name] = {"low": p.low, "high": p.high, "unit": p.unit}
    return result


@router.get("/simulator/status")
async def simulator_status(req: Request) -> dict:
    """Return current simulator running state."""
    simulator = req.app.state.simulator
    return {"running": not simulator.is_paused}


@router.post("/simulator/start")
async def simulator_start(req: Request) -> dict:
    """Start (resume) data generation."""
    simulator = req.app.state.simulator
    simulator.resume()
    return {"running": True}


@router.post("/simulator/stop")
async def simulator_stop(req: Request) -> dict:
    """Pause data generation."""
    simulator = req.app.state.simulator
    simulator.pause()
    return {"running": False}


@router.post("/simulator/inject")
async def inject_anomaly(
    req: Request,
    anomaly_type: AnomalyType = Query(...),
    line_id: int = Query(1, ge=1, le=2),
) -> dict:
    """Manually inject an anomaly scenario for demo/testing."""
    simulator = req.app.state.simulator  # type: ignore[attr-defined]
    return simulator.inject_anomaly(anomaly_type, line_id)
