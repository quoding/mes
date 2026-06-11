from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.correlation import compute_correlation_matrix, compute_cross_station_correlations

router = APIRouter(prefix="/correlation", tags=["correlation"])


@router.get("/matrix")
async def correlation_matrix(
    db: Annotated[AsyncSession, Depends(get_db)],
    line_id: int = Query(1, ge=1, le=2),
    station: str = Query("coating"),
    window_minutes: int = Query(30, ge=5, le=1440),
) -> list[dict]:
    return await compute_correlation_matrix(db, line_id, station, window_minutes)


@router.get("/cross-station")
async def cross_station(
    db: Annotated[AsyncSession, Depends(get_db)],
    line_id: int = Query(1, ge=1, le=2),
    window_minutes: int = Query(60, ge=10, le=1440),
) -> list[dict]:
    return await compute_cross_station_correlations(db, line_id, window_minutes)
