"""Layer 4 failure signature rule table — pure data, no logic.

Each FailureSignature is an AND-combination of "atom conditions" describing a
deviation from the learned baseline (see signature_engine.py for evaluation).
Adding a new failure mode only requires adding an entry here.
"""
from __future__ import annotations

from dataclasses import dataclass

# (station, param) pair type
ParamKey = tuple[str, str]
PairKey = tuple[ParamKey, ParamKey]


@dataclass(frozen=True)
class AtomCond:
    kind: str          # CORR_BREAK | CORR_FLIP | CORR_EMERGE | TREND_UP | TREND_DOWN | VAR_SPIKE | OSC
    target: PairKey | ParamKey


@dataclass(frozen=True)
class FailureSignature:
    id: str
    name_ko: str
    severity: str       # WARNING | CRITICAL
    conditions: list[AtomCond]
    action_ko: str
    related_equipment_station: str
    min_conditions: int | None = None  # None=전부 필요, n이면 n개 이상 (부분 매칭)


FAILURE_SIGNATURES: list[FailureSignature] = [
    FailureSignature(
        id="BEARING_WEAR", name_ko="캘린더 롤 베어링 마모 의심", severity="CRITICAL",
        conditions=[
            AtomCond("OSC", ("calendering", "roll_pressure")),
            AtomCond("CORR_BREAK", (("calendering", "roll_pressure"), ("calendering", "electrode_density"))),
        ],
        action_ko="롤 베어링 진동 측정 및 윤활 상태 점검, 교체 일정 수립",
        related_equipment_station="calendering",
    ),
    FailureSignature(
        id="GAP_WEAR", name_ko="코팅 다이 갭 마모 의심", severity="WARNING",
        conditions=[
            AtomCond("CORR_BREAK", (("coating", "slurry_viscosity"), ("coating", "coating_thickness"))),
            AtomCond("TREND_UP", ("coating", "coating_thickness")),
        ],
        action_ko="다이 갭 측정 및 재조정, 두께 프로파일 확인",
        related_equipment_station="coating",
    ),
    FailureSignature(
        id="SLURRY_DEGRADE", name_ko="슬러리 경시 열화 의심", severity="WARNING",
        conditions=[
            AtomCond("TREND_UP", ("coating", "slurry_viscosity")),
            AtomCond("CORR_EMERGE", (("coating", "slurry_viscosity"), ("coating", "coating_thickness"))),
        ],
        min_conditions=1,   # 추세만으로도 1차 경보 (신뢰도 하향)
        action_ko="슬러리 교반 강화, 온도 확인, 잔여 사용 기한 검토",
        related_equipment_station="coating",
    ),
    FailureSignature(
        id="HEATER_FAULT", name_ko="건조로 히터 제어 이상 의심", severity="CRITICAL",
        conditions=[
            AtomCond("VAR_SPIKE", ("coating", "dry_temp_zone2")),
            AtomCond("CORR_FLIP", (("coating", "dry_temp_zone2"), ("coating", "coating_thickness"))),
        ],
        action_ko="히터 SCR/열전대 점검, 건조 조건 재설정",
        related_equipment_station="coating",
    ),
]


def active_pairs() -> set[PairKey]:
    """페어 단위 상관 계산이 필요한 모든 페어 (CORR_* 조건)."""
    pairs: set[PairKey] = set()
    for sig in FAILURE_SIGNATURES:
        for cond in sig.conditions:
            if cond.kind.startswith("CORR_"):
                pairs.add(cond.target)  # type: ignore[arg-type]
    return pairs


def active_params() -> set[ParamKey]:
    """단변량 통계(추세/분산/주기성) 또는 상관 계산에 필요한 모든 (station, param)."""
    params: set[ParamKey] = set()
    for sig in FAILURE_SIGNATURES:
        for cond in sig.conditions:
            if cond.kind.startswith("CORR_"):
                a, b = cond.target  # type: ignore[misc]
                params.add(a)
                params.add(b)
            else:
                params.add(cond.target)  # type: ignore[arg-type]
    return params
