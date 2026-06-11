"""AlertGate 상태머신 테스트 — RAISED/ACTIVE/UPDATED/RESOLVED 수명주기."""
from __future__ import annotations

from app.services.failure_rules import FAILURE_SIGNATURES
from app.services.signature_engine import RESOLVE_MISSES

SIG = FAILURE_SIGNATURES[0]  # BEARING_WEAR
LINE = 1


async def match(eng, conf=0.8):
    return await eng._gate(LINE, SIG, True, conf, [{"kind": "OSC"}])


async def miss(eng):
    return await eng._gate(LINE, SIG, False, 0.0, [])


async def test_first_match_raises(sig_engine):
    ev = await match(sig_engine)
    assert ev["event"] == "RAISED"


async def test_repeat_match_updates_no_duplicate(sig_engine):
    await match(sig_engine)
    for _ in range(3):
        ev = await match(sig_engine)
        assert ev["event"] == "UPDATED"
    raised = [e for e in sig_engine.captured if e["event"] == "RAISED"]
    assert len(raised) == 1, "진행 중인 한 고장은 RAISED를 한 번만 발행해야 함"


async def test_resolve_after_consecutive_misses(sig_engine):
    await match(sig_engine)
    events = [await miss(sig_engine) for _ in range(RESOLVE_MISSES)]
    assert events[-1]["event"] == "RESOLVED"
    assert all(e is None for e in events[:-1])


async def test_rearm_within_cooldown_goes_active(sig_engine):
    """RESOLVED 직후 재발 → 새 RAISED가 아니라 ACTIVE (플래핑 방지)."""
    await match(sig_engine)
    for _ in range(RESOLVE_MISSES):
        await miss(sig_engine)
    ev = await match(sig_engine)
    assert ev["event"] == "ACTIVE"


async def test_rearm_expired_raises_fresh(sig_engine):
    await match(sig_engine)
    for _ in range(RESOLVE_MISSES):
        await miss(sig_engine)
    for _ in range(10):  # REARM_COOLDOWN_EVALS 소진
        await miss(sig_engine)
    ev = await match(sig_engine)
    assert ev["event"] == "RAISED"
