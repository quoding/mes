"""E2E: 시뮬레이터에 고장 시나리오 주입 → Layer 4 시그니처 탐지 검증.

시뮬레이터를 실시간 sleep 없이 틱 단위로 구동하고, 매 틱 SignatureEngine에
공급한다. 워밍업으로 베이스라인을 형성한 뒤 이상을 주입하고, 해당 고장
시그니처가 RAISED 되는지 + 탐지 지연(틱)을 측정한다.
"""
from __future__ import annotations

import pytest

from app.services.signature_engine import SignatureEngine
from app.services.simulator import ActiveAnomaly, AnomalyType, ProcessSimulator

WARMUP_TICKS = 1300       # 윈도우(600) 채우기 + 베이스라인 EWMA 수렴
DETECT_TICKS = 900        # 주입 후 탐지 허용 한도 (= 7.5분 상당)


async def drive(sim: ProcessSimulator, eng: SignatureEngine, ticks: int,
                events_out: list | None = None, tick_offset: int = 0) -> None:
    for t in range(ticks):
        readings = sim.compute_tick_readings()
        eng.ingest(readings)
        if eng.should_eval():
            before = len(eng.captured)
            await eng.evaluate()
            if events_out is not None:
                for ev in eng.captured[before:]:
                    events_out.append((tick_offset + t, ev))


def inject(sim: ProcessSimulator, atype: AnomalyType, station: str, param: str,
           ticks: int, line: int = 1) -> None:
    sim._active_anomalies.append(ActiveAnomaly(
        anomaly_type=atype, line_id=line, station=station, param=param,
        ticks_remaining=ticks, magnitude=1.2))


async def warmed_up(sim, sig_engine):
    await drive(sim, sig_engine, WARMUP_TICKS)
    assert not [e for e in sig_engine.captured if e["event"] == "RAISED"], \
        "워밍업(정상 운전) 중 오탐 발생"
    sig_engine.captured.clear()


def first_raise(events, signature_id, line=1):
    for tick, ev in events:
        if ev["signature_id"] == signature_id and ev["event"] in ("RAISED", "ACTIVE") \
                and ev["line_id"] == line:
            return tick, ev
    return None


@pytest.mark.parametrize("atype,station,param,duration,expected_sig", [
    (AnomalyType.PRESSURE_OSC, "calendering", "roll_pressure", 900, "BEARING_WEAR"),
    (AnomalyType.TEMP_DEVIATION, "coating", "dry_temp_zone2", 900, "HEATER_FAULT"),
    (AnomalyType.THICKNESS_DRIFT, "coating", "coating_thickness", 600, "GAP_WEAR"),
    (AnomalyType.VISCOSITY_RISE, "coating", "slurry_viscosity", 600, "SLURRY_DEGRADE"),
])
async def test_injected_failure_is_detected(sim, sig_engine, atype, station, param,
                                            duration, expected_sig):
    await warmed_up(sim, sig_engine)
    events: list = []
    inject(sim, atype, station, param, duration)
    await drive(sim, sig_engine, DETECT_TICKS, events_out=events)

    hit = first_raise(events, expected_sig)
    assert hit is not None, (
        f"{atype.value} 주입 후 {DETECT_TICKS}틱 내 {expected_sig} 미탐지. "
        f"발생 이벤트: {[(t, e['signature_id'], e['event']) for t, e in events]}"
    )
    tick, ev = hit
    print(f"\n[탐지 성능] {atype.value} → {expected_sig}: "
          f"{tick}틱 ({tick * 0.5:.0f}초) / confidence={ev['confidence']}")


async def test_no_false_positive_30min(sim, sig_engine):
    """정상 운전 30분(3600틱) 동안 RAISED 0건 — 오탐율 증명."""
    await drive(sim, sig_engine, WARMUP_TICKS + 3600)
    raised = [e for e in sig_engine.captured if e["event"] == "RAISED"]
    assert raised == [], f"정상 운전 중 오탐: {[(e['signature_id'], e['line_id']) for e in raised]}"


async def test_alert_resolves_after_anomaly_ends(sim, sig_engine):
    await warmed_up(sim, sig_engine)
    events: list = []
    inject(sim, AnomalyType.PRESSURE_OSC, "calendering", "roll_pressure", 600)
    # 이상 600틱 + 윈도우 정화 + RESOLVE_MISSES 여유분까지 구동
    await drive(sim, sig_engine, 2400, events_out=events)

    assert first_raise(events, "BEARING_WEAR") is not None
    resolved = [ev for _, ev in events
                if ev["signature_id"] == "BEARING_WEAR" and ev["event"] == "RESOLVED"]
    assert resolved, "이상 종료 후 알림이 RESOLVED로 전환되어야 함"
