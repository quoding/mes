"""Real-time parameter correlation analysis using TimescaleDB time-bucketing."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from scipy import stats
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.simulator import STATION_PARAMS

logger = logging.getLogger(__name__)

# Pre-define interesting cross-station pairs (domain knowledge)
DOMAIN_PAIRS = [
    ("coating", "slurry_viscosity", "coating", "coating_thickness"),
    ("coating", "tension_supply",   "coating", "coating_weight"),
    ("coating", "dry_temp_zone2",   "coating", "coating_thickness"),
    ("coating", "line_speed",       "coating", "coating_weight"),
    ("coating", "coating_thickness","calendering", "electrode_density"),
    ("calendering", "roll_pressure","calendering", "electrode_density"),
    ("calendering", "roll_temperature", "calendering", "thickness_after"),
]


def _interpret(r: float, p: float) -> str:
    if p > 0.05:
        return "통계적으로 유의하지 않음"
    ar = abs(r)
    direction = "양의" if r > 0 else "음의"
    if ar >= 0.8:
        return f"매우 강한 {direction} 상관 (r={r:.2f})"
    if ar >= 0.6:
        return f"강한 {direction} 상관 (r={r:.2f})"
    if ar >= 0.4:
        return f"중간 {direction} 상관 (r={r:.2f})"
    return f"약한 {direction} 상관 (r={r:.2f})"


async def compute_correlation_matrix(
    db: AsyncSession,
    line_id: int = 1,
    station: str = "coating",
    window_minutes: int = 30,
) -> list[dict]:
    """Compute Pearson correlation between all parameter pairs within a station."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    # Fetch raw data for the station
    rows = await db.execute(
        text("""
            SELECT param, value
            FROM process_data
            WHERE line_id = :line AND station = :station AND time >= :since
            ORDER BY time
        """),
        {"line": line_id, "station": station, "since": since},
    )
    data: dict[str, list[float]] = {}
    for param, value in rows:
        data.setdefault(param, []).append(value)

    if not data:
        return []

    # Only keep params with enough samples
    params = [k for k, v in data.items() if len(v) >= 20]
    results: list[dict] = []

    for i, pa in enumerate(params):
        for pb in params[i + 1:]:
            a, b = np.array(data[pa]), np.array(data[pb])
            min_len = min(len(a), len(b))
            if min_len < 10:
                continue
            a, b = a[:min_len], b[:min_len]
            try:
                r, p_value = stats.pearsonr(a, b)
            except Exception:
                continue
            results.append({
                "param_a": pa,
                "param_b": pb,
                "r": round(float(r), 4),
                "p_value": round(float(p_value), 6),
                "interpretation": _interpret(float(r), float(p_value)),
                "abs_r": round(abs(float(r)), 4),
            })

    return sorted(results, key=lambda x: x["abs_r"], reverse=True)


async def compute_cross_station_correlations(
    db: AsyncSession,
    line_id: int = 1,
    window_minutes: int = 60,
) -> list[dict]:
    """Compute predefined domain-knowledge cross-station correlations."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    results: list[dict] = []

    for sta_a, pa, sta_b, pb in DOMAIN_PAIRS:
        rows_a = await db.execute(
            text("SELECT value FROM process_data WHERE line_id=:l AND station=:s AND param=:p AND time>=:t ORDER BY time"),
            {"l": line_id, "s": sta_a, "p": pa, "t": since},
        )
        rows_b = await db.execute(
            text("SELECT value FROM process_data WHERE line_id=:l AND station=:s AND param=:p AND time>=:t ORDER BY time"),
            {"l": line_id, "s": sta_b, "p": pb, "t": since},
        )
        va = [r[0] for r in rows_a]
        vb = [r[0] for r in rows_b]
        min_len = min(len(va), len(vb))
        if min_len < 10:
            continue
        try:
            r, p_value = stats.pearsonr(va[:min_len], vb[:min_len])
        except Exception:
            continue
        results.append({
            "station_a": sta_a,
            "param_a": pa,
            "station_b": sta_b,
            "param_b": pb,
            "r": round(float(r), 4),
            "p_value": round(float(p_value), 6),
            "interpretation": _interpret(float(r), float(p_value)),
        })

    return results
