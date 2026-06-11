"""Layer 1 (Z-score) / Layer 2 (EWMA) 단위 테스트 — _ParamState는 순수 클래스."""
from __future__ import annotations

import numpy as np

from app.services.anomaly_engine import _ParamState

LOW, HIGH = 80.0, 120.0
MID = (LOW + HIGH) / 2


def feed(state: _ParamState, values) -> list[dict]:
    return [state.update(float(v)) for v in values]


def test_zscore_spike_critical():
    state = _ParamState(LOW, HIGH)
    rng = np.random.default_rng(1)
    feed(state, MID + rng.normal(0, 0.5, 50))
    result = state.update(MID + 0.5 * 8)  # +8σ 스파이크
    assert result.get("zscore", {}).get("severity") == "CRITICAL"


def test_zscore_normal_no_alarm():
    state = _ParamState(LOW, HIGH)
    # 결정적 ±1σ 패턴 — 스파이크 없음
    values = [MID + 0.5 * ((-1) ** i) for i in range(200)]
    results = feed(state, values)
    assert all("zscore" not in r for r in results)


def test_ewma_catches_slow_drift_zscore_misses():
    """계층 존재 이유: 느린 드리프트는 Z-score가 못 잡고 EWMA가 잡는다."""
    state = _ParamState(LOW, HIGH)
    rng = np.random.default_rng(2)
    sigma = 0.5
    feed(state, MID + rng.normal(0, sigma, 100))  # 정상 워밍업
    drift = MID + rng.normal(0, sigma, 150) + np.arange(150) * (0.1 * sigma)
    results = feed(state, drift)

    zscore_hits = [r for r in results if "zscore" in r]
    ewma_hits = [r for r in results if "ewma" in r]
    assert not zscore_hits, "느린 드리프트에 Z-score가 반응하면 안 됨"
    assert ewma_hits, "EWMA 제어차트는 느린 드리프트를 잡아야 함"


def test_threshold_severity_bands():
    state = _ParamState(LOW, HIGH)
    assert state.update(HIGH * 1.06)["threshold"]["severity"] == "WARNING"
    state2 = _ParamState(LOW, HIGH)
    assert state2.update(HIGH * 1.16)["threshold"]["severity"] == "CRITICAL"


def test_threshold_normal_value_silent():
    state = _ParamState(LOW, HIGH)
    assert "threshold" not in state.update(MID)
