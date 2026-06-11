"""Layer 4 atom 판정(_compute_atoms) 단위 테스트 — 합성 시계열 + 주입 베이스라인."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.signature_engine import MIN_SAMPLES, WINDOW_TICKS, SignatureEngine
from tests.conftest import fill_window, make_series

LINE = 1
VISC = ("coating", "slurry_viscosity")
THICK = ("coating", "coating_thickness")
TEMP = ("coating", "dry_temp_zone2")
PRESS = ("calendering", "roll_pressure")
DENS = ("calendering", "electrode_density")
PAIR_VT = (VISC, THICK)
PAIR_PD = (PRESS, DENS)
PAIR_TT = (TEMP, THICK)


@pytest.fixture
def eng(sig_engine: SignatureEngine) -> SignatureEngine:
    """모든 active param 윈도우를 무상관 정상 노이즈로 채우고 베이스라인을 중립으로 주입."""
    rng = np.random.default_rng(7)
    for i, (st, pa) in enumerate(sorted(sig_engine._params)):
        fill_window(sig_engine, LINE, st, pa, make_series(WINDOW_TICKS, 100.0, 1.0, rng=rng))
        sig_engine._std_baseline[(LINE, (st, pa))] = 1.0
    for pair in sig_engine._pairs:
        sig_engine._corr_baseline[(LINE, pair)] = 0.0
    return sig_engine


def correlated(n: int, r_target: float, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    a = rng.normal(0, 1, n)
    b = r_target * a + np.sqrt(1 - r_target**2) * rng.normal(0, 1, n)
    return 100 + a, 100 + b


def atoms_of(eng: SignatureEngine) -> set:
    atoms, _, _ = eng._compute_atoms(LINE)
    return set(atoms.keys())


def test_corr_break(eng):
    eng._corr_baseline[(LINE, PAIR_VT)] = 0.7  # 평소 강한 상관이었는데
    # 윈도우는 이미 무상관 노이즈 → r_now ≈ 0
    assert ("CORR_BREAK", PAIR_VT) in atoms_of(eng)


def test_corr_flip(eng):
    eng._corr_baseline[(LINE, PAIR_TT)] = 0.6
    a, b = correlated(WINDOW_TICKS, -0.6)
    fill_window(eng, LINE, *TEMP, a)
    fill_window(eng, LINE, *THICK, b)
    assert ("CORR_FLIP", PAIR_TT) in atoms_of(eng)


def test_corr_emerge(eng):
    eng._corr_baseline[(LINE, PAIR_VT)] = 0.1
    a, b = correlated(WINDOW_TICKS, 0.85)
    fill_window(eng, LINE, *VISC, a)
    fill_window(eng, LINE, *THICK, b)
    assert ("CORR_EMERGE", PAIR_VT) in atoms_of(eng)


def test_var_spike(eng):
    fill_window(eng, LINE, *TEMP, make_series(WINDOW_TICKS, 100.0, 3.5))  # std 3.5 > 2.5×1.0
    assert ("VAR_SPIKE", TEMP) in atoms_of(eng)


def test_trend_up_down(eng):
    # dry_temp_zone2 정상범위 100~130 → slope 임계 = 2×30/600 = 0.1
    fill_window(eng, LINE, *TEMP, make_series(WINDOW_TICKS, 100.0, 0.4, slope=0.15))
    assert ("TREND_UP", TEMP) in atoms_of(eng)
    fill_window(eng, LINE, *TEMP, make_series(WINDOW_TICKS, 100.0, 0.4, slope=-0.15))
    assert ("TREND_DOWN", TEMP) in atoms_of(eng)


def test_osc(eng):
    fill_window(eng, LINE, *PRESS,
                make_series(WINDOW_TICKS, 300.0, 1.0, osc_period=40, osc_amp=5.0))
    atoms, _, _ = eng._compute_atoms(LINE)
    assert ("OSC", PRESS) in atoms
    assert atoms[("OSC", PRESS)]["evidence"]["lag"] > 0


def test_no_atoms_on_normal(eng):
    # 베이스라인을 현재 상태와 일치시키면 atom이 없어야 함 (오탐 0)
    atoms, corr_now, std_now = eng._compute_atoms(LINE)
    for pair, r in corr_now.items():
        eng._corr_baseline[(LINE, pair)] = r
    for param, s in std_now.items():
        eng._std_baseline[(LINE, param)] = s
    assert atoms_of(eng) == set()


async def test_warmup_skip(sig_engine):
    # MIN_SAMPLES 미만이면 평가 자체를 건너뛴다
    for (st, pa) in sig_engine._params:
        fill_window(sig_engine, LINE, st, pa, make_series(MIN_SAMPLES - 10, 100.0, 1.0))
    assert await sig_engine._evaluate_line(LINE) == []


async def test_baseline_isolation(eng):
    """한 파라미터의 atom이 무관한 파라미터의 베이스라인 학습을 막지 않는다 (버그 수정 회귀)."""
    # coating 점도에 TREND 유발
    visc_def_range = 2000.0  # 3000~5000
    fill_window(eng, LINE, *VISC,
                make_series(WINDOW_TICKS, 4000.0, 20.0, slope=2 * visc_def_range / WINDOW_TICKS * 2))
    before = eng._corr_baseline[(LINE, PAIR_PD)]
    _, corr_now, _ = eng._compute_atoms(LINE)
    await eng._evaluate_line(LINE)
    after = eng._corr_baseline[(LINE, PAIR_PD)]
    # 무관한 calendering 페어 베이스라인은 corr_now 방향으로 갱신되어야 함
    assert after != before
    assert abs(after - corr_now[PAIR_PD] * 0.02 - before * 0.98) < 1e-9
