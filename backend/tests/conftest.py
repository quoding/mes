"""Shared fixtures: DB/Redis 없이 시뮬레이터·탐지 엔진을 구동한다."""
from __future__ import annotations

import random
from collections import deque

import numpy as np
import pytest

from app.services.signature_engine import WINDOW_TICKS, SignatureEngine
from app.services.simulator import ProcessSimulator


@pytest.fixture(autouse=True)
def fixed_seed():
    """재현성: 모든 테스트는 고정 시드로 시작한다."""
    random.seed(42)
    np.random.seed(42)


@pytest.fixture
def sim() -> ProcessSimulator:
    return ProcessSimulator()


@pytest.fixture
def sig_engine(monkeypatch) -> SignatureEngine:
    """DB/Redis persist를 가로채 발행 이벤트를 .captured 리스트에 수집."""
    eng = SignatureEngine()
    eng.captured = []  # type: ignore[attr-defined]

    async def fake_persist(line, sig, state, event_type):
        payload = {
            "signature_id": sig.id,
            "event": event_type,
            "state": state.state,
            "line_id": line,
            "confidence": state.confidence,
            "evidence": state.evidence,
        }
        eng.captured.append(payload)  # type: ignore[attr-defined]
        return payload

    monkeypatch.setattr(eng, "_persist_and_publish", fake_persist)
    return eng


def fill_window(eng: SignatureEngine, line: int, station: str, param: str, values) -> None:
    eng._windows[(line, station, param)] = deque(values, maxlen=WINDOW_TICKS)


def make_series(n: int, mean: float = 0.0, std: float = 1.0, slope: float = 0.0,
                osc_period: int | None = None, osc_amp: float = 0.0,
                rng: np.random.Generator | None = None) -> np.ndarray:
    rng = rng or np.random.default_rng(0)
    x = np.arange(n, dtype=float)
    out = mean + rng.normal(0, std, n) + slope * x
    if osc_period:
        out += osc_amp * np.sin(2 * np.pi * x / osc_period)
    return out
