"""Three-layer anomaly detection engine.

Layer 1 — Z-score:    Per-parameter rolling statistics (fast, stateless).
Layer 2 — EWMA chart: Exponentially weighted moving average control chart.
                      Catches slow drift that Z-score misses.
Layer 3 — Isolation Forest: Multivariate anomaly over all params per station.
                            Runs on a 5-minute batch.

Detection results are persisted to anomaly_events and published to Redis
channel 'anomaly:live' for WebSocket broadcast.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

import numpy as np
import redis.asyncio as aioredis
from sklearn.ensemble import IsolationForest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.redis import get_pool
from app.models.anomaly import AnomalyEvent
from app.services.predictive import _extract_features
from app.services.signature_engine import signature_engine
from app.services.simulator import LINE_IDS, STATION_PARAMS

logger = logging.getLogger(__name__)
settings = get_settings()

ANOMALY_CHANNEL = "anomaly:live"

# Rolling window sizes
ZSCORE_WINDOW = 50       # ticks
EWMA_LAMBDA = 0.2        # smoothing factor
EWMA_L = 3.0             # control limit multiplier (σ)
IF_BATCH_TICKS = 600     # ≈5 min at 0.5s interval

# 같은 (line, station, param, pattern_type) 조합에 대한 중복 이벤트 억제 기간(초)
EVENT_COOLDOWN_SECONDS = 60.0


class _ParamState:
    """Rolling statistics for one parameter on one line+station."""

    def __init__(self, low: float, high: float) -> None:
        self.low = low
        self.high = high
        self.buf: deque[float] = deque(maxlen=ZSCORE_WINDOW)
        # EWMA state
        self.ewma: float | None = None
        # Initial variance: model the full range as ±2σ (uniform-ish distribution).
        # Previous (/6)² estimate was too tight → UCL/LCL barely outside midpoint
        # → flagged normal operating values as anomalies.
        self.ewma_var: float = ((high - low) / 4) ** 2

    def update(self, value: float) -> dict[str, Any]:
        """Update state and return anomaly info dict (empty if normal)."""
        self.buf.append(value)
        result: dict[str, Any] = {}

        # ── Layer 1: Z-score ─────────────────────────────────────────────────
        if len(self.buf) >= 10:
            arr = np.array(self.buf)
            mu, sigma = float(arr.mean()), float(arr.std())
            if sigma > 1e-9:
                z = abs(value - mu) / sigma
                if z > 4.0:
                    result["zscore"] = {"z": round(z, 2), "severity": "CRITICAL"}
                elif z > 3.0:
                    result["zscore"] = {"z": round(z, 2), "severity": "WARNING"}

        # ── Layer 2: EWMA control chart ──────────────────────────────────────
        if self.ewma is None:
            self.ewma = value
        else:
            self.ewma = EWMA_LAMBDA * value + (1 - EWMA_LAMBDA) * self.ewma

        # 분산 온라인 갱신 (EWMA of squared deviation from EWMA mean)
        deviation = value - self.ewma
        self.ewma_var = EWMA_LAMBDA * (deviation ** 2) + (1 - EWMA_LAMBDA) * self.ewma_var

        sigma_ewma = (self.ewma_var * EWMA_LAMBDA / (2 - EWMA_LAMBDA)) ** 0.5
        # 중심선: 충분한 샘플이 쌓이면 공정 롤링 평균, 아니면 정상범위 중앙값으로 워밍업
        center = float(np.mean(self.buf)) if len(self.buf) >= 10 else (self.low + self.high) / 2
        ucl = center + EWMA_L * sigma_ewma
        lcl = center - EWMA_L * sigma_ewma

        if self.ewma > ucl or self.ewma < lcl:
            result["ewma"] = {
                "ewma": round(self.ewma, 4),
                "ucl": round(ucl, 4),
                "lcl": round(lcl, 4),
                "severity": "WARNING",
            }

        # Simple threshold check (INFO level)
        if value > self.high * 1.05 or value < self.low * 0.95:
            result["threshold"] = {
                "severity": "CRITICAL" if (value > self.high * 1.15 or value < self.low * 0.85) else "WARNING"
            }

        return result


class AnomalyEngine:
    def __init__(self) -> None:
        # States: line_id → station → param → _ParamState
        self._states: dict[int, dict[str, dict[str, _ParamState]]] = {}
        for line in LINE_IDS:
            self._states[line] = {}
            for station, params in STATION_PARAMS.items():
                self._states[line][station] = {}
                for p in params:
                    self._states[line][station][p.name] = _ParamState(p.low, p.high)

        # IF batch buffers: line → station → list of param vectors
        self._if_buffers: dict[str, list[list[float]]] = {}
        self._if_tick = 0
        self._if_models: dict[str, IsolationForest] = {}

        # 이벤트 dedup: (line, station, param, pattern_type) → 마지막 발행 시각(epoch seconds)
        self._last_event_time: dict[tuple[int, str, str, str], float] = {}

        self._redis: aioredis.Redis | None = None
        self._running = False

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """Subscribe to process:live and run detection on every batch."""
        self._running = True
        pool = get_pool()
        self._redis = aioredis.Redis(connection_pool=pool)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("process:live")
        logger.info("AnomalyEngine started")

        signature_engine.set_redis(self._redis)
        await signature_engine.restore_baselines()

        try:
            async for message in pubsub.listen():
                if not self._running:
                    break
                if message["type"] != "message":
                    continue
                readings: list[dict] = json.loads(message["data"])
                events = await self._process_batch(readings)
                if events:
                    await self._persist_and_publish(events)

                signature_engine.ingest(readings)
                if signature_engine.should_eval():
                    try:
                        await signature_engine.evaluate()
                    except Exception:
                        logger.exception("SignatureEngine evaluation failed")
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe("process:live")
            await pubsub.aclose()

    async def _process_batch(self, readings: list[dict]) -> list[dict]:
        """Run per-param detection and accumulate IF vectors."""
        events: list[dict] = []
        by_station: dict[str, dict[str, float]] = {}  # "line:station" → {param: value}

        for r in readings:
            line, station, param, value = r["line_id"], r["station"], r["param"], r["value"]
            state = self._states.get(line, {}).get(station, {}).get(param)
            if state is None:
                continue

            result = state.update(value)
            if result:
                # Pick highest severity
                severities = [v["severity"] for v in result.values() if "severity" in v]
                severity = "CRITICAL" if "CRITICAL" in severities else "WARNING"
                method = list(result.keys())[0]
                pattern_type = f"LAYER1_{method.upper()}"

                # 동일 (line, station, param, pattern_type) 조합은 cooldown 동안 중복 기록 안 함
                dedup_key = (line, station, param, pattern_type)
                now_ts = datetime.fromisoformat(r["time"]).timestamp()
                last_ts = self._last_event_time.get(dedup_key)
                if last_ts is not None and (now_ts - last_ts) < EVENT_COOLDOWN_SECONDS:
                    continue
                self._last_event_time[dedup_key] = now_ts

                events.append({
                    "detected_at": r["time"],
                    "line_id": line,
                    "station": station,
                    "severity": severity,
                    "param": param,
                    "value": value,
                    "threshold_low": state.low,
                    "threshold_high": state.high,
                    "pattern_type": pattern_type,
                    "feature_snapshot": json.dumps(_extract_features(list(state.buf))),
                })

            # Accumulate for IF
            key = f"{line}:{station}"
            if key not in by_station:
                by_station[key] = {}
            by_station[key][param] = value

        # Add vectors to IF buffer
        for key, param_dict in by_station.items():
            params = STATION_PARAMS[key.split(":")[1]]
            vec = [param_dict.get(p.name, (p.low + p.high) / 2) for p in params]
            if key not in self._if_buffers:
                self._if_buffers[key] = []
            self._if_buffers[key].append(vec)

        # Periodic IF batch run
        self._if_tick += 1
        if self._if_tick >= IF_BATCH_TICKS:
            self._if_tick = 0
            if_events = self._run_isolation_forest()
            events.extend(if_events)

        return events

    def _run_isolation_forest(self) -> list[dict]:
        events: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        for key, vectors in self._if_buffers.items():
            if len(vectors) < 50:
                continue
            X = np.array(vectors)
            try:
                model = IsolationForest(contamination=0.05, random_state=42, n_jobs=-1)
                scores = model.fit_predict(X)
                # Check recent 20 ticks
                recent_scores = scores[-20:]
                anomaly_ratio = (recent_scores == -1).mean()
                if anomaly_ratio > 0.4:
                    line_id, station = key.split(":")
                    events.append({
                        "detected_at": now,
                        "line_id": int(line_id),
                        "station": station,
                        "severity": "WARNING",
                        "param": "multivariate",
                        "value": float(anomaly_ratio),
                        "threshold_low": None,
                        "threshold_high": 0.4,
                        "pattern_type": "LAYER3_ISOLATION_FOREST",
                    })
            except Exception:
                logger.exception("IF error for %s", key)

        # Clear buffers after run
        self._if_buffers.clear()
        return events

    async def _persist_and_publish(self, events: list[dict]) -> None:
        async with AsyncSessionLocal() as session:
            for ev in events:
                row = AnomalyEvent(
                    detected_at=datetime.fromisoformat(ev["detected_at"]),
                    line_id=ev["line_id"],
                    station=ev["station"],
                    severity=ev["severity"],
                    param=ev["param"],
                    value=ev["value"],
                    threshold_low=ev.get("threshold_low"),
                    threshold_high=ev.get("threshold_high"),
                    pattern_type=ev.get("pattern_type"),
                    feature_snapshot=ev.get("feature_snapshot"),
                )
                session.add(row)
            await session.commit()

        # Publish to WebSocket subscribers
        if self._redis:
            await self._redis.publish(ANOMALY_CHANNEL, json.dumps(events))


# Singleton
anomaly_engine = AnomalyEngine()
