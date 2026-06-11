"""시뮬레이터 검증 — 정상범위, 인과결합이 실제 상관을 만드는지, 이상 수명."""
from __future__ import annotations

import numpy as np
from scipy import stats

from app.services.simulator import (
    STATION_PARAMS,
    ActiveAnomaly,
    AnomalyType,
    Coupling,
    ProcessSimulator,
)


def run_ticks(sim: ProcessSimulator, n: int) -> list[list[dict]]:
    return [sim.compute_tick_readings() for _ in range(n)]


def collect(batches, line, station, param) -> np.ndarray:
    return np.array([
        r["value"] for batch in batches for r in batch
        if r["line_id"] == line and r["station"] == station and r["param"] == param
    ])


def test_normal_values_stay_near_range(sim):
    batches = run_ticks(sim, 500)
    for station, params in STATION_PARAMS.items():
        for p in params:
            vals = collect(batches, 1, station, p.name)
            span = p.high - p.low
            assert vals.min() > p.low - span * 0.3, f"{station}.{p.name} too low"
            assert vals.max() < p.high + span * 0.3, f"{station}.{p.name} too high"


def test_coupling_produces_correlation(sim):
    """Coupling이 단순 장식이 아니라 실측 가능한 상관을 만든다는 증명."""
    batches = run_ticks(sim, 800)
    visc = collect(batches, 1, "coating", "slurry_viscosity")
    thick = collect(batches, 1, "coating", "coating_thickness")
    speed = collect(batches, 1, "coating", "line_speed")
    weight = collect(batches, 1, "coating", "coating_weight")
    press = collect(batches, 1, "calendering", "roll_pressure")
    dens = collect(batches, 1, "calendering", "electrode_density")

    assert stats.pearsonr(visc, thick).statistic > 0.3
    assert stats.pearsonr(speed, weight).statistic < -0.3
    assert stats.pearsonr(press, dens).statistic > 0.4


def test_gain_override_during_anomaly(sim):
    c = Coupling(("coating", "slurry_viscosity"), ("coating", "coating_thickness"), gain=0.6)
    assert sim._effective_gain(c, 1) == 0.6
    sim._active_anomalies.append(ActiveAnomaly(
        AnomalyType.THICKNESS_DRIFT, 1, "coating", "coating_thickness", ticks_remaining=100))
    assert sim._effective_gain(c, 1) == 0.1
    assert sim._effective_gain(c, 2) == 0.6, "다른 라인은 영향 없어야 함"


def test_anomaly_lifetime_exact(sim):
    """ticks=N으로 주입한 이상은 정확히 N틱 동안만 활성 (off-by-one 회귀)."""
    sim._active_anomalies.append(ActiveAnomaly(
        AnomalyType.TENSION_SPIKE, 1, "coating", "tension_supply", ticks_remaining=20))
    active_ticks = 0
    for _ in range(30):
        if sim._active_anomalies:
            active_ticks += 1
        sim.compute_tick_readings()
    assert active_ticks == 20


def test_inject_anomaly_api(sim):
    info = sim.inject_anomaly(AnomalyType.PRESSURE_OSC, line_id=2)
    assert info["station"] == "calendering"
    assert sim._active_anomalies[0].line_id == 2
