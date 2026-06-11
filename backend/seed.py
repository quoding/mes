"""Seed script: insert equipment records and historical anomaly patterns.

Run once after DB init:
    python seed.py
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal, init_db
from app.models.anomaly import AnomalyEvent
from app.models.equipment import Equipment


EQUIPMENT_SEED = [
    # Line 1
    {"name": "코팅기 #1 메인롤", "line_id": 1, "station": "coating", "total_hours": 8760.0},
    {"name": "건조로 #1 히터", "line_id": 1, "station": "coating", "total_hours": 6500.0},
    {"name": "캘린더 #1 롤", "line_id": 1, "station": "calendering", "total_hours": 9200.0},
    {"name": "슬리터 #1 칼날", "line_id": 1, "station": "slitting", "total_hours": 3200.0},
    {"name": "권취기 #1", "line_id": 1, "station": "winding", "total_hours": 7800.0},
    # Line 2
    {"name": "코팅기 #2 메인롤", "line_id": 2, "station": "coating", "total_hours": 5400.0},
    {"name": "건조로 #2 히터", "line_id": 2, "station": "coating", "total_hours": 4200.0},
    {"name": "캘린더 #2 롤", "line_id": 2, "station": "calendering", "total_hours": 6100.0},
    {"name": "슬리터 #2 칼날", "line_id": 2, "station": "slitting", "total_hours": 2900.0},
    {"name": "권취기 #2", "line_id": 2, "station": "winding", "total_hours": 5600.0},
]


ANOMALY_PATTERNS = [
    # (station, param, pattern_type, value_mult)
    ("coating",     "tension_supply",    "LAYER1_ZSCORE",  1.4),
    ("coating",     "slurry_viscosity",  "LAYER1_EWMA",    1.3),
    ("coating",     "coating_thickness", "LAYER1_ZSCORE",  0.7),
    ("calendering", "roll_pressure",     "LAYER3_ISOLATION_FOREST", 1.5),
    ("coating",     "dry_temp_zone2",    "LAYER1_THRESHOLD", 1.2),
]


async def seed():
    await init_db()
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(func.count()).select_from(Equipment))
        if existing:
            print(f"Seed skipped: equipment table already has {existing} rows")
            return

        # Equipment
        for eq_data in EQUIPMENT_SEED:
            last_maint = now - timedelta(days=random.randint(10, 60))
            next_maint = last_maint + timedelta(days=90)
            eq = Equipment(
                **eq_data,
                install_date=now - timedelta(days=random.randint(365, 1460)),
                last_maintenance=last_maint,
                next_maintenance=next_maint,
            )
            session.add(eq)

        # Historical anomaly events (90 days back)
        from app.services.simulator import STATION_PARAMS
        for _ in range(500):
            station, param, pattern, mult = random.choice(ANOMALY_PATTERNS)
            param_defs = {p.name: p for p in STATION_PARAMS.get(station, [])}
            p_def = param_defs.get(param)
            if not p_def:
                continue
            mid = (p_def.low + p_def.high) / 2
            value = mid * mult + random.gauss(0, p_def.noise_sigma * 3)
            severity = "CRITICAL" if abs(value - mid) > (p_def.high - p_def.low) * 0.4 else "WARNING"
            features = json.dumps({
                "mean": round(mid * random.uniform(0.95, 1.05), 3),
                "std": round(p_def.noise_sigma * random.uniform(2, 5), 3),
                "trend_slope": round(random.uniform(-0.01, 0.05), 5),
                "skewness": round(random.uniform(-1, 1), 3),
            })
            ev = AnomalyEvent(
                detected_at=now - timedelta(
                    days=random.randint(1, 90),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                ),
                line_id=random.choice([1, 2]),
                station=station,
                severity=severity,
                param=param,
                value=round(value, 3),
                threshold_low=p_def.low,
                threshold_high=p_def.high,
                pattern_type=pattern,
                feature_snapshot=features,
            )
            session.add(ev)

        await session.commit()
        print("Seed complete: equipment + 500 anomaly events")


if __name__ == "__main__":
    asyncio.run(seed())
