"""Roll-to-roll battery manufacturing process simulator.

Generates realistic sensor data for 2 production lines with 4 stations each:
coating → calendering → slitting → winding

Each station has configurable parameters with normal distributions + slow drift.
Anomaly injection simulates 5 failure scenarios found in real battery manufacturing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.redis import get_pool

logger = logging.getLogger(__name__)
settings = get_settings()

REDIS_CHANNEL = "process:live"
REDIS_LATEST_KEY = "process:latest"  # hash: line:{id}:{station}:{param} → value


# ── Parameter definitions ────────────────────────────────────────────────────

@dataclass
class ParamDef:
    name: str
    unit: str
    low: float        # normal range low
    high: float       # normal range high
    noise_sigma: float  # per-tick Gaussian noise σ
    drift_rate: float = 0.0  # slow drift per tick (simulates wear)


STATION_PARAMS: dict[str, list[ParamDef]] = {
    "coating": [
        ParamDef("line_speed",        "m/min",   15.0,  25.0,  0.15, 0.0),
        ParamDef("coating_thickness", "μm",      80.0,  120.0, 0.5,  0.001),
        ParamDef("coating_weight",    "mg/cm²",  15.0,  20.0,  0.08, 0.0),
        ParamDef("dry_temp_zone1",    "°C",      80.0,  100.0, 0.3,  0.0),
        ParamDef("dry_temp_zone2",    "°C",     100.0,  130.0, 0.4,  0.0),
        ParamDef("dry_temp_zone3",    "°C",     120.0,  150.0, 0.5,  0.0),
        ParamDef("tension_supply",    "N",       30.0,   50.0, 0.3,  0.0),
        ParamDef("tension_winding",   "N",       40.0,   60.0, 0.3,  0.0),
        ParamDef("slurry_viscosity",  "cP",    3000.0, 5000.0, 20.0, 0.05),
    ],
    "calendering": [
        ParamDef("roll_pressure",     "kN/m",   200.0,  400.0, 2.0,  0.02),
        ParamDef("roll_temperature",  "°C",      60.0,   80.0, 0.3,  0.0),
        ParamDef("electrode_density", "g/cm³",   1.5,    1.8,  0.005, 0.0),
        ParamDef("thickness_before",  "μm",     140.0,  180.0, 0.4,  0.0),
        ParamDef("thickness_after",   "μm",      80.0,  120.0, 0.3,  0.0),
        ParamDef("line_speed",        "m/min",   10.0,   20.0, 0.1,  0.0),
    ],
    "slitting": [
        ParamDef("line_speed",        "m/min",   30.0,   50.0, 0.2,  0.0),
        ParamDef("tension",           "N",       20.0,   40.0, 0.25, 0.0),
        ParamDef("slit_width_dev",    "mm",      -0.1,    0.1, 0.005, 0.0),
        ParamDef("blade_pressure",    "N",       10.0,   30.0, 0.2,  0.01),
    ],
    "winding": [
        ParamDef("tension",           "N",       20.0,   35.0, 0.2,  0.0),
        ParamDef("winding_speed",     "m/min",   20.0,   40.0, 0.2,  0.0),
        ParamDef("roll_diameter",     "mm",      50.0,  500.0, 0.1,  0.3),  # grows
        ParamDef("alignment_offset",  "mm",      -0.5,    0.5, 0.01, 0.0),
    ],
}

STATIONS = list(STATION_PARAMS.keys())
LINE_IDS = [1, 2]

# (station, param) → ParamDef, for coupling lookups
PARAM_LOOKUP: dict[tuple[str, str], ParamDef] = {
    (station, p.name): p
    for station, params in STATION_PARAMS.items()
    for p in params
}


# ── Causal couplings (Layer 4 prerequisite) ──────────────────────────────────
# 정상 운전 중 파라미터 간 물리적 인과관계를 인코딩한다. 고장 시 해당 결합의
# gain이 변조되어 "관계 붕괴/반전/출현"이 데이터에 나타난다 (signature_engine 참조).

@dataclass(frozen=True)
class Coupling:
    src: tuple[str, str]      # (station, param) — cause
    dst: tuple[str, str]      # (station, param) — effect
    gain: float               # dst 변화량 = gain × (src 정규화 편차) × dst noise_sigma
    lag_ticks: int = 0        # 공정 물리 지연


COUPLINGS: list[Coupling] = [
    # 점도가 오르면 같은 갭에서 두께 증가 (강한 양의 상관)
    Coupling(("coating", "slurry_viscosity"), ("coating", "coating_thickness"), gain=0.8),
    # 라인 속도가 빠르면 단위면적당 도포량 감소 (음의 상관)
    Coupling(("coating", "line_speed"), ("coating", "coating_weight"), gain=-0.5),
    # 건조 온도가 높으면 용매 증발↑ → 건조 후 두께 감소
    # (|r| ≥ 0.4가 되어야 Layer4 CORR_FLIP의 베이스라인 조건을 만족 — E2E 테스트로 검증된 값)
    Coupling(("coating", "dry_temp_zone2"), ("coating", "coating_thickness"), gain=-0.6),
    # 코팅 두께가 두꺼우면 캘린더링 후 밀도 상승 여지 (지연 결합)
    Coupling(("coating", "coating_thickness"), ("calendering", "electrode_density"), gain=0.4, lag_ticks=60),
    # 롤 압력이 높으면 전극 밀도 증가 (캘린더링 핵심 물리)
    Coupling(("calendering", "roll_pressure"), ("calendering", "electrode_density"), gain=0.7),
    # 롤 압력↑ → 압연 후 두께 감소
    Coupling(("calendering", "roll_pressure"), ("calendering", "thickness_after"), gain=-0.5),
]


# ── Anomaly types ────────────────────────────────────────────────────────────

class AnomalyType(str, Enum):
    TENSION_SPIKE      = "TENSION_SPIKE"       # 장력 급변 → 주름/파단
    THICKNESS_DRIFT    = "THICKNESS_DRIFT"     # 코팅 두께 점진 이탈
    TEMP_DEVIATION     = "TEMP_DEVIATION"      # 건조 온도 급변
    VISCOSITY_RISE     = "VISCOSITY_RISE"      # 슬러리 점도 상승
    PRESSURE_OSC       = "PRESSURE_OSC"        # 롤 압력 주기 진동 (베어링 마모)


# 고장 시나리오가 활성화되면 해당 결합의 gain을 일시적으로 변조한다 (인과 사슬:
# 고장 → 물리적 관계 변화 → 상관 변화 → Layer 4 탐지).
# {AnomalyType: {(coupling.src, coupling.dst): overridden_gain}}
COUPLING_GAIN_OVERRIDES: dict[AnomalyType, dict[tuple[tuple[str, str], tuple[str, str]], float]] = {
    # 갭 마모: 점도→두께 결합 붕괴 (상관 약화)
    AnomalyType.THICKNESS_DRIFT: {
        (("coating", "slurry_viscosity"), ("coating", "coating_thickness")): 0.1,
    },
    # 슬러리 열화: 점도→두께 결합 강화 (상관 출현/강화)
    AnomalyType.VISCOSITY_RISE: {
        (("coating", "slurry_viscosity"), ("coating", "coating_thickness")): 0.9,
    },
    # 베어링 마모: 압력 센서값이 실제 닙 하중과 분리 → 진동이 밀도에 전달되지 않음.
    # 0이 아니면 진동 진폭이 커서 잔여 gain만으로도 상관이 유지되어 CORR_BREAK가 불가능 (E2E로 검증)
    AnomalyType.PRESSURE_OSC: {
        (("calendering", "roll_pressure"), ("calendering", "electrode_density")): 0.0,
    },
    # 히터 제어 이상: 온도→두께 결합 부호 반전 (제어계 역작용)
    AnomalyType.TEMP_DEVIATION: {
        (("coating", "dry_temp_zone2"), ("coating", "coating_thickness")): 0.6,
    },
}


@dataclass
class ActiveAnomaly:
    anomaly_type: AnomalyType
    line_id: int
    station: str
    param: str
    ticks_remaining: int
    magnitude: float = 1.0
    phase: float = 0.0  # for oscillation
    total_ticks: int = 0  # 주입 시점의 전체 수명 (램프형 이상 진행률 계산용)

    def __post_init__(self) -> None:
        if self.total_ticks <= 0:
            self.total_ticks = self.ticks_remaining

    @property
    def progress(self) -> float:
        """0.0(시작) → 1.0(종료 직전) 진행률."""
        return 1.0 - self.ticks_remaining / self.total_ticks


# ── Simulator ────────────────────────────────────────────────────────────────

class ProcessSimulator:
    def __init__(self) -> None:
        self._running = False
        self._paused = True  # start paused; use resume() to begin data generation
        self._active_anomalies: list[ActiveAnomaly] = []

        # Per-line per-station per-param: current "center" value (with drift)
        self._centers: dict[str, float] = {}
        for line in LINE_IDS:
            for station, params in STATION_PARAMS.items():
                for p in params:
                    mid = (p.low + p.high) / 2
                    self._centers[f"{line}:{station}:{p.name}"] = mid

        # Redis client for publishing
        self._redis: aioredis.Redis | None = None
        self._db_tick: int = 0

        # Lag buffers for delayed couplings: (line_id, coupling_index) → deque[norm_dev]
        self._lag_buffers: dict[tuple[int, int], deque[float]] = {
            (line, i): deque(maxlen=c.lag_ticks)
            for line in LINE_IDS
            for i, c in enumerate(COUPLINGS)
            if c.lag_ticks > 0
        }

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True
        logger.info("ProcessSimulator paused")

    def resume(self) -> None:
        self._paused = False
        logger.info("ProcessSimulator resumed")

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        pool = get_pool()
        self._redis = aioredis.Redis(connection_pool=pool)
        interval = settings.simulator_interval_ms / 1000.0
        logger.info("ProcessSimulator started (interval=%.2fs)", interval)

        while self._running:
            if not self._paused:
                try:
                    await self._tick()
                except Exception:
                    logger.exception("Simulator tick error")
            await asyncio.sleep(interval)

        await self._redis.aclose()

    def compute_tick_readings(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """One simulation step: pure value computation, no I/O.

        Separated from _tick so detection logic can be tested tick-by-tick
        without Redis/DB.
        """
        now = now or datetime.now(timezone.utc)
        readings: list[dict[str, Any]] = []

        # Pass 1: independent values (drift + noise + direct anomaly injection)
        raw: dict[tuple[int, str, str], float] = {}
        centers: dict[tuple[int, str, str], float] = {}
        for line in LINE_IDS:
            for station, params in STATION_PARAMS.items():
                for p in params:
                    key = f"{line}:{station}:{p.name}"
                    value, center = self._compute_value(key, p, line, station, now)
                    raw[(line, station, p.name)] = value
                    centers[(line, station, p.name)] = center

        # Pass 2: apply causal couplings on top of pass-1 values
        final = dict(raw)
        for line in LINE_IDS:
            for i, c in enumerate(COUPLINGS):
                src_def = PARAM_LOOKUP[c.src]
                dst_def = PARAM_LOOKUP[c.dst]
                src_key = (line, *c.src)
                dst_key = (line, *c.dst)

                norm_dev = (raw[src_key] - centers[src_key]) / src_def.noise_sigma

                if c.lag_ticks > 0:
                    dq = self._lag_buffers[(line, i)]
                    dq.append(norm_dev)
                    norm_dev = dq[0] if len(dq) == dq.maxlen else 0.0

                gain = self._effective_gain(c, line)
                final[dst_key] += gain * norm_dev * dst_def.noise_sigma

        for line in LINE_IDS:
            for station, params in STATION_PARAMS.items():
                for p in params:
                    value = final[(line, station, p.name)]
                    readings.append({
                        "time": now.isoformat(),
                        "line_id": line,
                        "station": station,
                        "param": p.name,
                        "value": round(value, 4),
                        "unit": p.unit,
                    })

        # Anomaly lifetime: consume one tick *after* applying, then drop expired,
        # so an anomaly injected with ticks=N affects exactly N ticks.
        for a in self._active_anomalies:
            a.ticks_remaining -= 1
            a.phase += 0.3  # for oscillation
        self._active_anomalies = [a for a in self._active_anomalies if a.ticks_remaining > 0]

        return readings

    async def _tick(self) -> None:
        readings = self.compute_tick_readings()

        # Publish to Redis channel (all clients consume in real-time)
        payload = json.dumps(readings)
        await self._redis.publish(REDIS_CHANNEL, payload)

        # Update latest values hash for REST API polling
        pipe = self._redis.pipeline()
        for r in readings:
            hkey = f"line:{r['line_id']}:{r['station']}:{r['param']}"
            pipe.hset(REDIS_LATEST_KEY, hkey, json.dumps({"value": r["value"], "unit": r["unit"], "time": r["time"]}))
        await pipe.execute()

        # Persist to TimescaleDB every 10 ticks (~5 seconds) to avoid write spam
        self._db_tick += 1
        if self._db_tick % 10 == 0:
            await self._persist_readings(readings)

        # Random anomaly injection
        if random.random() < settings.anomaly_inject_prob:
            atype = random.choice(list(AnomalyType))
            self._inject(atype, random.choice(LINE_IDS))

    def _compute_value(
        self, key: str, p: ParamDef, line: int, station: str, now: datetime
    ) -> tuple[float, float]:
        center = self._centers[key]

        # Apply drift
        center += p.drift_rate * random.gauss(0, 1)
        # Clamp center within ±20% beyond range
        margin = (p.high - p.low) * 0.2
        center = max(p.low - margin, min(p.high + margin, center))
        self._centers[key] = center

        # Gaussian noise
        value = center + random.gauss(0, p.noise_sigma)

        # Apply active anomalies
        for anomaly in self._active_anomalies:
            if anomaly.line_id != line or anomaly.station != station or anomaly.param != p.name:
                continue
            value = self._apply_anomaly(anomaly, p, value, now)

        return value, center

    def _effective_gain(self, coupling: "Coupling", line: int) -> float:
        """활성 이상이 이 결합의 gain을 변조하는지 확인 (인과 사슬 붕괴/강화/반전)."""
        for anomaly in self._active_anomalies:
            if anomaly.line_id != line:
                continue
            overrides = COUPLING_GAIN_OVERRIDES.get(anomaly.anomaly_type)
            if not overrides:
                continue
            override = overrides.get((coupling.src, coupling.dst))
            if override is not None:
                return override
        return coupling.gain

    def _apply_anomaly(self, anomaly: ActiveAnomaly, p: ParamDef, value: float, now: datetime) -> float:
        span = p.high - p.low
        t = anomaly.anomaly_type

        if t == AnomalyType.TENSION_SPIKE:
            # Sudden large deviation
            return value + span * anomaly.magnitude * random.choice([-1, 1])

        if t == AnomalyType.THICKNESS_DRIFT:
            # Gradual drift toward max boundary over the anomaly's lifetime
            return value + span * anomaly.magnitude * anomaly.progress

        if t == AnomalyType.TEMP_DEVIATION:
            # Step change + control-loop instability (sustained variance spike)
            return value + span * 0.4 * anomaly.magnitude + random.gauss(0, span * 0.06)

        if t == AnomalyType.VISCOSITY_RISE:
            # Monotone rise over lifetime (경시 열화 — 서서히 누적)
            return value + span * 1.2 * anomaly.magnitude * anomaly.progress

        if t == AnomalyType.PRESSURE_OSC:
            # Sinusoidal oscillation
            return value + span * 0.2 * math.sin(anomaly.phase) * anomaly.magnitude

        return value

    def inject_anomaly(self, anomaly_type: AnomalyType, line_id: int = 1) -> dict:
        """External API to inject a specific anomaly scenario."""
        # Layer 4는 5분(600틱) 윈도우의 상관/추세를 보므로, 시그니처 대상 이상은
        # 윈도우와 비슷한 시간 규모로 지속되어야 탐지 가능하다 (E2E 테스트 기준).
        configs: dict[AnomalyType, tuple[str, str, int]] = {
            AnomalyType.TENSION_SPIKE:   ("coating",     "tension_supply",    20),
            AnomalyType.THICKNESS_DRIFT: ("coating",     "coating_thickness", 600),
            AnomalyType.TEMP_DEVIATION:  ("coating",     "dry_temp_zone2",    600),
            AnomalyType.VISCOSITY_RISE:  ("coating",     "slurry_viscosity",  600),
            AnomalyType.PRESSURE_OSC:    ("calendering", "roll_pressure",     600),
        }
        station, param, ticks = configs[anomaly_type]
        anomaly = ActiveAnomaly(
            anomaly_type=anomaly_type,
            line_id=line_id,
            station=station,
            param=param,
            ticks_remaining=ticks,
            magnitude=random.uniform(0.8, 1.4),
        )
        self._active_anomalies.append(anomaly)
        logger.info("Injected anomaly: %s on line %d %s.%s", anomaly_type, line_id, station, param)
        return {"anomaly_type": anomaly_type, "line_id": line_id, "station": station, "param": param, "ticks": ticks}

    def _inject(self, anomaly_type: AnomalyType, line_id: int) -> None:
        self.inject_anomaly(anomaly_type, line_id)

    async def _persist_readings(self, readings: list[dict[str, Any]]) -> None:
        """Batch-insert readings into TimescaleDB."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.process import ProcessData
            from datetime import datetime

            async with AsyncSessionLocal() as session:
                session.add_all(
                    ProcessData(
                        time=datetime.fromisoformat(r["time"]),
                        line_id=r["line_id"],
                        station=r["station"],
                        param=r["param"],
                        value=r["value"],
                        unit=r["unit"],
                    )
                    for r in readings
                )
                await session.commit()
        except Exception:
            logger.warning("DB persist failed — readings dropped for this batch", exc_info=True)

    def get_param_thresholds(self) -> dict[str, dict[str, dict[str, float]]]:
        """Return normal ranges for all params — used by anomaly engine."""
        result: dict[str, dict[str, dict[str, float]]] = {}
        for station, params in STATION_PARAMS.items():
            result[station] = {}
            for p in params:
                result[station][p.name] = {"low": p.low, "high": p.high}
        return result
