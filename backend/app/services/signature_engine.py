"""Layer 4 — correlation-pattern based failure signature engine.

Layer 1-3 (anomaly_engine) ask "is this value wrong?". Layer 4 asks
"is the *relationship* between values wrong?". It ingests the same
process:live tick stream, keeps a rolling window per (line, station, param)
and a slowly-adapting EWMA baseline of correlations/variances, and every
EVAL_EVERY_TICKS evaluates FAILURE_SIGNATURES (failure_rules.py) against
deviations from that baseline.

Matches go through an AlertGate state machine (RAISED -> ACTIVE -> RESOLVED)
so that one ongoing failure produces exactly one alert record, and are
persisted to failure_alerts + published on Redis channel 'alert:live'.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import redis.asyncio as aioredis
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.alert import FailureAlert
from app.models.equipment import Equipment
from app.services.failure_rules import (
    FAILURE_SIGNATURES,
    FailureSignature,
    PairKey,
    ParamKey,
    active_pairs,
    active_params,
)
from app.services.simulator import LINE_IDS, PARAM_LOOKUP

logger = logging.getLogger(__name__)

ALERT_CHANNEL = "alert:live"

WINDOW_TICKS = 600          # 5분 @ 0.5s — 상관/추세 계산 윈도우
EVAL_EVERY_TICKS = 60       # 30초마다 규칙 평가
BASELINE_ALPHA = 0.02       # 베이스라인 EWMA 갱신 계수 (시정수 ≈ 25분)
MIN_SAMPLES = 300           # 워밍업: 이 샘플 수 미만이면 평가 skip

CORR_BREAK_BASE = 0.5
CORR_BREAK_NOW = 0.3
CORR_FLIP_MIN = 0.4
CORR_EMERGE_BASE = 0.3
CORR_EMERGE_NOW = 0.6
VAR_SPIKE_M = 2.5           # std_now > m * std_base
TREND_K = 1.0               # |slope| > k * (high-low)/WINDOW_TICKS — 윈도우당 1×span 변화
                            # (2.0이면 어떤 램프형 이상도 못 잡음 — E2E 오탐 테스트가 하한 안전성 보증)
OSC_THRESHOLD = 0.6         # autocorrelation r(lag) >= 0.6
OSC_LAGS = range(10, 100, 5)

RESOLVE_MISSES = 4          # 연속 4회(2분) 미매칭 → RESOLVED
REARM_COOLDOWN_EVALS = 10   # RESOLVED 후 10회(5분) 동안 재발생 시 ACTIVE로 복귀 (플래핑 방지)

BASELINE_REDIS_KEY = "sig:baseline:{line}"


def _pair_key(pair: PairKey) -> str:
    (sa, pa), (sb, pb) = pair
    return f"{sa}.{pa}|{sb}.{pb}"


def _decode_pair(s: str) -> PairKey | None:
    try:
        a, b = s.split("|")
        sa, pa = a.split(".")
        sb, pb = b.split(".")
        return ((sa, pa), (sb, pb))
    except Exception:
        return None


def _param_key(p: ParamKey) -> str:
    return f"{p[0]}.{p[1]}"


def _decode_param(s: str) -> ParamKey | None:
    try:
        sa, pa = s.split(".")
        return (sa, pa)
    except Exception:
        return None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _max_autocorr(arr: np.ndarray, lags: range) -> tuple[float, int]:
    """Return (max |autocorrelation|, lag) over the given lag range."""
    n = len(arr)
    centered = arr - arr.mean()
    denom = float(np.sum(centered ** 2))
    if denom < 1e-9:
        return 0.0, 0
    best_r, best_lag = 0.0, 0
    for lag in lags:
        if lag >= n:
            break
        r = float(np.sum(centered[:-lag] * centered[lag:]) / denom)
        if abs(r) > abs(best_r):
            best_r, best_lag = r, lag
    return best_r, best_lag


@dataclass
class AlertState:
    state: str  # RAISED | ACTIVE | RESOLVED
    confidence: float
    evidence: list[dict]
    raised_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    miss_count: int = 0
    rearm_evals_left: int = 0
    db_id: int | None = None


class SignatureEngine:
    def __init__(self) -> None:
        self._pairs: set[PairKey] = active_pairs()
        self._params: set[ParamKey] = active_params()
        self._windows: dict[tuple[int, str, str], deque[float]] = {
            (line, st, pa): deque(maxlen=WINDOW_TICKS)
            for line in LINE_IDS
            for (st, pa) in self._params
        }
        self._corr_baseline: dict[tuple[int, PairKey], float] = {}
        self._std_baseline: dict[tuple[int, ParamKey], float] = {}
        self._tick_count = 0
        self._alert_states: dict[tuple[int, str], AlertState] = {}
        self._redis: aioredis.Redis | None = None

    def set_redis(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    # ── Baseline persistence (cold-start recovery) ──────────────────────────

    async def restore_baselines(self) -> None:
        if self._redis is None:
            return
        for line in LINE_IDS:
            raw = await self._redis.get(BASELINE_REDIS_KEY.format(line=line))
            if not raw:
                continue
            try:
                data = json.loads(raw)
                for k, v in data.get("corr", {}).items():
                    pair = _decode_pair(k)
                    if pair:
                        self._corr_baseline[(line, pair)] = v
                for k, v in data.get("std", {}).items():
                    param = _decode_param(k)
                    if param:
                        self._std_baseline[(line, param)] = v
            except Exception:
                logger.exception("Failed to restore signature baseline for line %d", line)

    async def _persist_baselines(self, line: int) -> None:
        if self._redis is None:
            return
        data = {
            "corr": {_pair_key(p): v for (l, p), v in self._corr_baseline.items() if l == line},
            "std": {_param_key(p): v for (l, p), v in self._std_baseline.items() if l == line},
        }
        await self._redis.set(BASELINE_REDIS_KEY.format(line=line), json.dumps(data))

    # ── Engine status (for /alerts/engine-status) ───────────────────────────

    def status(self) -> dict:
        result = {}
        for line in LINE_IDS:
            sample_len = min(
                (len(self._windows[(line, s, p)]) for (s, p) in self._params),
                default=0,
            )
            result[str(line)] = {
                "warmed_up": sample_len >= MIN_SAMPLES,
                "samples": sample_len,
                "min_samples": MIN_SAMPLES,
                "baseline_pairs": sum(1 for (l, _p) in self._corr_baseline if l == line),
                "baseline_params": sum(1 for (l, _p) in self._std_baseline if l == line),
            }
        return result

    async def reset_baseline(self, line: int | None = None) -> None:
        lines = [line] if line is not None else LINE_IDS
        for ln in lines:
            for k in [k for k in self._corr_baseline if k[0] == ln]:
                del self._corr_baseline[k]
            for k in [k for k in self._std_baseline if k[0] == ln]:
                del self._std_baseline[k]
            if self._redis is not None:
                await self._redis.delete(BASELINE_REDIS_KEY.format(line=ln))

    # ── Tick ingestion ───────────────────────────────────────────────────────

    def ingest(self, readings: list[dict]) -> None:
        for r in readings:
            key = (r["line_id"], r["station"], r["param"])
            if key in self._windows:
                self._windows[key].append(r["value"])
        self._tick_count += 1

    def should_eval(self) -> bool:
        return self._tick_count % EVAL_EVERY_TICKS == 0

    # ── Evaluation ───────────────────────────────────────────────────────────

    async def evaluate(self) -> list[dict]:
        events: list[dict] = []
        for line in LINE_IDS:
            events.extend(await self._evaluate_line(line))
        return events

    async def _evaluate_line(self, line: int) -> list[dict]:
        sample_len = min(
            (len(self._windows[(line, s, p)]) for (s, p) in self._params),
            default=0,
        )
        if sample_len < MIN_SAMPLES:
            return []

        atoms, corr_now, std_now_map = self._compute_atoms(line)
        return await self._finish_eval(line, atoms, corr_now, std_now_map)

    def _compute_atoms(
        self, line: int
    ) -> tuple[dict[tuple[str, object], dict], dict[PairKey, float], dict[ParamKey, float]]:
        """Compute deviation atoms vs baseline. Pure computation — unit-testable."""
        # atoms[(kind, target)] = {"strength": float, "evidence": dict}
        atoms: dict[tuple[str, object], dict] = {}
        corr_now: dict[PairKey, float] = {}

        for pair in self._pairs:
            (sa, pa), (sb, pb) = pair
            a = np.array(self._windows[(line, sa, pa)])
            b = np.array(self._windows[(line, sb, pb)])
            if a.std() < 1e-9 or b.std() < 1e-9:
                r_now = 0.0
            else:
                r_now = float(np.corrcoef(a, b)[0, 1])
            corr_now[pair] = r_now

            r_base = self._corr_baseline.get((line, pair))
            if r_base is None:
                continue

            if abs(r_base) >= CORR_BREAK_BASE and abs(r_now) < CORR_BREAK_NOW:
                strength = _clamp01((abs(r_base) - abs(r_now)) / (abs(r_base) - CORR_BREAK_NOW + 1e-9))
                atoms[("CORR_BREAK", pair)] = {
                    "strength": strength,
                    "evidence": {
                        "kind": "CORR_BREAK", "pair": _pair_key(pair),
                        "r_baseline": round(r_base, 3), "r_now": round(r_now, 3),
                        "delta": round(r_now - r_base, 3),
                    },
                }

            if (r_base * r_now < 0) and abs(r_base) >= CORR_FLIP_MIN and abs(r_now) >= CORR_FLIP_MIN:
                strength = _clamp01((abs(r_base) + abs(r_now)) / 2)
                atoms[("CORR_FLIP", pair)] = {
                    "strength": strength,
                    "evidence": {
                        "kind": "CORR_FLIP", "pair": _pair_key(pair),
                        "r_baseline": round(r_base, 3), "r_now": round(r_now, 3),
                    },
                }

            if abs(r_base) < CORR_EMERGE_BASE and abs(r_now) >= CORR_EMERGE_NOW:
                strength = _clamp01((abs(r_now) - CORR_EMERGE_NOW) / (1.0 - CORR_EMERGE_NOW + 1e-9) + 0.5)
                atoms[("CORR_EMERGE", pair)] = {
                    "strength": _clamp01(strength),
                    "evidence": {
                        "kind": "CORR_EMERGE", "pair": _pair_key(pair),
                        "r_baseline": round(r_base, 3), "r_now": round(r_now, 3),
                    },
                }

        std_now_map: dict[ParamKey, float] = {}
        for param in self._params:
            arr = np.array(self._windows[(line, *param)])
            std_now = float(arr.std())
            std_now_map[param] = std_now

            x = np.arange(len(arr))
            slope = float(np.polyfit(x, arr, 1)[0])
            p_def = PARAM_LOOKUP[param]
            slope_threshold = TREND_K * (p_def.high - p_def.low) / WINDOW_TICKS

            if slope > slope_threshold:
                atoms[("TREND_UP", param)] = {
                    "strength": _clamp01(slope / slope_threshold / 2),
                    "evidence": {"kind": "TREND_UP", "param": _param_key(param), "slope": round(slope, 5)},
                }
            elif slope < -slope_threshold:
                atoms[("TREND_DOWN", param)] = {
                    "strength": _clamp01(abs(slope) / slope_threshold / 2),
                    "evidence": {"kind": "TREND_DOWN", "param": _param_key(param), "slope": round(slope, 5)},
                }

            std_base = self._std_baseline.get((line, param))
            if std_base and std_base > 1e-9 and std_now > VAR_SPIKE_M * std_base:
                strength = _clamp01((std_now / std_base - 1) / (VAR_SPIKE_M - 1))
                atoms[("VAR_SPIKE", param)] = {
                    "strength": strength,
                    "evidence": {
                        "kind": "VAR_SPIKE", "param": _param_key(param),
                        "std_now": round(std_now, 4), "std_baseline": round(std_base, 4),
                    },
                }

            osc_r, osc_lag = _max_autocorr(arr, OSC_LAGS)
            if abs(osc_r) >= OSC_THRESHOLD:
                atoms[("OSC", param)] = {
                    "strength": _clamp01(abs(osc_r)),
                    "evidence": {
                        "kind": "OSC", "param": _param_key(param),
                        "lag": osc_lag, "autocorr": round(osc_r, 3),
                    },
                }

        return atoms, corr_now, std_now_map

    async def _finish_eval(
        self,
        line: int,
        atoms: dict[tuple[str, object], dict],
        corr_now: dict[PairKey, float],
        std_now_map: dict[ParamKey, float],
    ) -> list[dict]:
        """Baseline update + signature matching + alert gating."""
        # ── Baseline update (self-immune: skip params implicated in an atom) ──
        # Isolation is per-param: an unrelated trend elsewhere must not freeze
        # the whole line's baseline learning.
        disturbed: set[ParamKey] = set()
        for (kind, target) in atoms:
            if kind.startswith("CORR_"):
                a_key, b_key = target  # type: ignore[misc]
                disturbed.add(a_key)
                disturbed.add(b_key)
            else:
                disturbed.add(target)  # type: ignore[arg-type]

        for pair in self._pairs:
            key = (line, pair)
            if key not in self._corr_baseline:
                self._corr_baseline[key] = corr_now[pair]
            elif pair[0] not in disturbed and pair[1] not in disturbed:
                self._corr_baseline[key] = (1 - BASELINE_ALPHA) * self._corr_baseline[key] + BASELINE_ALPHA * corr_now[pair]
        for param in self._params:
            key = (line, param)
            if key not in self._std_baseline:
                self._std_baseline[key] = std_now_map[param]
            elif param not in disturbed:
                self._std_baseline[key] = (1 - BASELINE_ALPHA) * self._std_baseline[key] + BASELINE_ALPHA * std_now_map[param]
        await self._persist_baselines(line)

        # ── Match signatures + AlertGate ─────────────────────────────────────
        events: list[dict] = []
        for sig in FAILURE_SIGNATURES:
            matched_atoms = [atoms.get((c.kind, c.target)) for c in sig.conditions]
            matched_count = sum(1 for m in matched_atoms if m is not None)
            required = sig.min_conditions if sig.min_conditions is not None else len(sig.conditions)
            matched = matched_count >= required and matched_count > 0

            confidence = 0.0
            evidence: list[dict] = []
            if matched:
                strengths = [m["strength"] for m in matched_atoms if m is not None]
                evidence = [m["evidence"] for m in matched_atoms if m is not None]
                confidence = sum(strengths) / len(strengths)
                if sig.min_conditions is not None:
                    confidence *= matched_count / len(sig.conditions)
                confidence = round(_clamp01(confidence), 3)

            ev = await self._gate(line, sig, matched, confidence, evidence)
            if ev:
                events.append(ev)

        return events

    # ── AlertGate state machine ──────────────────────────────────────────────

    async def _gate(
        self, line: int, sig: FailureSignature, matched: bool, confidence: float, evidence: list[dict]
    ) -> dict | None:
        key = (line, sig.id)
        prev = self._alert_states.get(key)
        now = datetime.now(timezone.utc)

        if matched:
            if prev is None or prev.state == "RESOLVED":
                new_state = "ACTIVE" if (prev and prev.rearm_evals_left > 0) else "RAISED"
                state = AlertState(
                    state=new_state, confidence=confidence, evidence=evidence,
                    raised_at=now, last_seen_at=now,
                    db_id=prev.db_id if prev else None,
                )
                self._alert_states[key] = state
                return await self._persist_and_publish(line, sig, state, "RAISED" if new_state == "RAISED" else "ACTIVE")

            # already RAISED or ACTIVE → update in place
            prev.state = "ACTIVE"
            prev.confidence = confidence
            prev.evidence = evidence
            prev.last_seen_at = now
            prev.miss_count = 0
            return await self._persist_and_publish(line, sig, prev, "UPDATED")

        # not matched this round
        if prev is None:
            return None

        if prev.state in ("RAISED", "ACTIVE"):
            prev.miss_count += 1
            if prev.miss_count >= RESOLVE_MISSES:
                prev.state = "RESOLVED"
                prev.resolved_at = now
                prev.rearm_evals_left = REARM_COOLDOWN_EVALS
                return await self._persist_and_publish(line, sig, prev, "RESOLVED")
            return None

        if prev.state == "RESOLVED" and prev.rearm_evals_left > 0:
            prev.rearm_evals_left -= 1
        return None

    async def _persist_and_publish(
        self, line: int, sig: FailureSignature, state: AlertState, event_type: str
    ) -> dict:
        evidence_json = json.dumps(state.evidence, ensure_ascii=False)

        async with AsyncSessionLocal() as session:
            if state.db_id is None:
                row = FailureAlert(
                    signature_id=sig.id,
                    line_id=line,
                    severity=sig.severity,
                    confidence=state.confidence,
                    state=state.state,
                    evidence=evidence_json,
                    raised_at=state.raised_at,
                    last_seen_at=state.last_seen_at,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                state.db_id = row.id
            else:
                row = await session.get(FailureAlert, state.db_id)
                if row is not None:
                    row.confidence = state.confidence
                    row.state = state.state
                    row.evidence = evidence_json
                    row.last_seen_at = state.last_seen_at
                    if state.state == "RESOLVED":
                        row.resolved_at = state.resolved_at
                    await session.commit()

            eq_result = await session.execute(
                select(Equipment.id).where(
                    Equipment.line_id == line, Equipment.station == sig.related_equipment_station
                )
            )
            equipment_ids = list(eq_result.scalars().all())

        payload = {
            "type": "failure_alert",
            "event": event_type,
            "alert_id": state.db_id,
            "signature_id": sig.id,
            "name": sig.name_ko,
            "severity": sig.severity,
            "state": state.state,
            "line_id": line,
            "confidence": state.confidence,
            "raised_at": state.raised_at.isoformat(),
            "last_seen_at": state.last_seen_at.isoformat(),
            "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
            "evidence": state.evidence,
            "action": sig.action_ko,
            "equipment_ids": equipment_ids,
        }

        if self._redis is not None:
            await self._redis.publish(ALERT_CHANNEL, json.dumps(payload, ensure_ascii=False))

        return payload


# Singleton
signature_engine = SignatureEngine()
