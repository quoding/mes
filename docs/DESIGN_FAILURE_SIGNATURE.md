# 설계: 상관분석 기반 실시간 고장 예측 알림 (Layer 4)

> LLM 없이, 파라미터 간 **상관 패턴의 변화**를 고장 시그니처로 매핑하여 실시간 알림을 발행하는 규칙 엔진.
> LLM은 알림 클릭 시 상세 분석을 요청하는 선택적 후속 단계로만 사용.
> 작성일: 2026-06-10

---

## 1. 목표와 비목표

### 목표
- 실시간 공정 데이터에서 **고장 전조 패턴**(베어링 마모, 슬러리 열화, 히터 불량 등)을 LLM 호출 없이 탐지
- 탐지 결과를 `{고장 유형, 신뢰도, 수치 근거, 권장 조치}` 형태로 WebSocket 푸시 → 프론트 알림(토스트/배너)
- 판정 로직은 결정론적: 같은 입력 → 같은 알림 (제조 현장 신뢰성 요구사항)
- 틱당 연산 비용 O(파라미터 수 × 윈도우) 수준으로 가볍게 유지

### 비목표
- 머신러닝 모델 학습/서빙 (Isolation Forest는 기존 Layer 3 유지, 새 모델 추가 안 함)
- 단일 파라미터 임계 초과 탐지 (Layer 1~2가 이미 담당 — 중복 구현 금지)
- 자동 조치 실행 (알림까지만; 조치는 사람 또는 향후 휴먼인더루프 에이전트)

---

## 2. 핵심 아이디어

Layer 1~3은 "값이 이상하다"를 본다. Layer 4는 **"관계가 이상하다"**를 본다.

```
정상 운전:  slurry_viscosity ↔ coating_thickness   r ≈ +0.7  (점도 오르면 두께 오름)
고장 전조:  같은 페어                                r ≈ +0.1  (관계 붕괴 — 갭 마모로 두께가 점도를 안 따라감)
```

절대 r값이 아니라 **베이스라인 대비 이탈**(Δr)을 신호로 쓴다. 이유:
- 절대 r은 라인/제품마다 다르다 → 임계값 하나로 일반화 불가
- 고장 전조는 대부분 "평소 있던 상관이 약화/반전"되거나 "평소 없던 상관이 출현"하는 형태
- 베이스라인은 시스템이 정상 운전 중에 스스로 학습 (콜드스타트 섹션 7 참조)

이탈 유형 3종을 시그니처의 원자 조건(primitive)으로 정의한다:

| 원자 조건 | 정의 | 의미 |
|---|---|---|
| `CORR_BREAK` | \|r_baseline\| ≥ 0.5 이고 \|r_now\| < 0.3 | 평소 상관 붕괴 |
| `CORR_FLIP` | sign(r_now) ≠ sign(r_baseline) 이고 양쪽 \|r\| ≥ 0.4 | 상관 부호 반전 |
| `CORR_EMERGE` | \|r_baseline\| < 0.3 이고 \|r_now\| ≥ 0.6 | 평소 없던 상관 출현 |

여기에 단변량 추세 원자 조건을 결합한다 (predictive.py의 `_extract_features`와 동일 통계 재사용):

| 원자 조건 | 정의 |
|---|---|
| `TREND_UP` / `TREND_DOWN` | 윈도우 내 선형회귀 slope가 (high−low)/윈도우길이 의 ±k배 초과 |
| `VAR_SPIKE` | rolling std가 베이스라인 std의 m배 초과 (m=2.5) |
| `OSC` | 자기상관 r(lag=k)가 0.6 이상인 주기성 존재 (FFT 불필요, lag 스캔으로 충분) |

**시그니처 = 원자 조건들의 AND 조합 + 메타데이터(고장명, 심각도, 권장 조치).**

---

## 3. 전체 아키텍처

```
                      ┌──────────────────────────────────────────────┐
                      │ anomaly_engine.py (기존 프로세스, Layer 추가)    │
process:live ────────▶│  Layer 1  Z-score          (기존)             │
 (Redis pub/sub,      │  Layer 2  EWMA             (기존)             │
  0.5s 틱)            │  Layer 3  IsolationForest  (기존, 5분 배치)     │
                      │  Layer 4  FailureSignature (신규, 30s 배치)  ──┼──┐
                      └──────────────────────────────────────────────┘  │
                                                                        │
        ┌───────────────────────────────────────────────────────────────┘
        │
        ▼
  SignatureEngine
  ├─ RollingWindow      파라미터별 deque(maxlen=600)  # 5분 @ 0.5s
  ├─ BaselineStore      페어별 r_baseline, 파라미터별 std_baseline (Redis hash, EWMA 갱신)
  ├─ RuleEvaluator      FAILURE_SIGNATURES 테이블 평가
  └─ AlertGate          cooldown + 상태머신 (RAISED → ACTIVE → RESOLVED)
        │
        ├─▶ DB: failure_alerts 테이블 (이력/감사)
        └─▶ Redis publish "alert:live" ──▶ ws.py /ws/alerts ──▶ 프론트 토스트/배너
```

설계 결정:
- **별도 서비스가 아니라 `anomaly_engine` 내부의 Layer 4로 구현.** 이미 `process:live`를 구독하고 틱 데이터를 받고 있으므로 구독자를 늘릴 이유가 없다. 파일은 분리(`services/signature_engine.py`)하되 호출은 `AnomalyEngine._process_batch()`에서.
- **DB가 아니라 인메모리 윈도우에서 상관 계산.** 기존 `correlation.py`는 매번 DB를 조회하는데, 30초마다 페어 수만큼 쿼리하는 건 낭비. 어차피 틱 스트림이 손에 있으므로 deque에 쌓는다. (기존 `correlation.py`는 REST API용으로 그대로 유지.)
- **알림 채널 분리 (`alert:live` ≠ `anomaly:live`).** 이상 이벤트는 초당 수 건 발생 가능한 저수준 신호, 고장 알림은 분 단위의 고수준 판정. 프론트에서 구독을 나눠야 토스트 스팸을 막을 수 있다.

---

## 4. 시뮬레이터 선행 작업: 인과 결합 (필수)

현재 `simulator.py`의 파라미터들은 **서로 독립적인 가우시안**이라 정상 상태에서 상관이 거의 0이다.
"정상 시 상관 존재 → 고장 시 붕괴" 스토리가 데이터에 나타나려면 인과 결합이 필요하다.

### 4-1. 결합 정의

`STATION_PARAMS`와 별도로 결합 테이블 추가:

```python
# simulator.py
@dataclass
class Coupling:
    src: tuple[str, str]      # (station, param) — 원인
    dst: tuple[str, str]      # (station, param) — 결과
    gain: float               # dst 변화량 = gain × (src 정규화 편차)
    lag_ticks: int = 0        # 공정 물리 지연 (코팅→캘린더링은 수십 초)

COUPLINGS: list[Coupling] = [
    # 점도가 오르면 같은 갭에서 두께 증가 (강한 양의 상관)
    Coupling(("coating", "slurry_viscosity"), ("coating", "coating_thickness"), gain=0.6),
    # 라인 속도가 빠르면 단위면적당 도포량 감소 (음의 상관)
    Coupling(("coating", "line_speed"), ("coating", "coating_weight"), gain=-0.5),
    # 건조 온도가 높으면 용매 증발↑ → 건조 후 두께 미세 감소
    Coupling(("coating", "dry_temp_zone2"), ("coating", "coating_thickness"), gain=-0.3),
    # 코팅 두께가 두꺼우면 캘린더링 후 밀도 상승 여지 (지연 결합)
    Coupling(("coating", "coating_thickness"), ("calendering", "electrode_density"), gain=0.4, lag_ticks=60),
    # 롤 압력이 높으면 전극 밀도 증가 (캘린더링 핵심 물리)
    Coupling(("calendering", "roll_pressure"), ("calendering", "electrode_density"), gain=0.7),
    # 롤 압력↑ → 압연 후 두께 감소
    Coupling(("calendering", "roll_pressure"), ("calendering", "thickness_after"), gain=-0.5),
]
```

### 4-2. `_compute_value` 수정

```python
# _tick에서: 1패스로 모든 "원인" 파라미터의 정규화 편차를 먼저 계산
#            2패스에서 결합 적용 — 순서 의존성 제거
norm_dev = (value_src - center_src) / noise_sigma_src   # 원인의 표준화 편차
value_dst += coupling.gain * norm_dev * noise_sigma_dst # 결과에 같은 스케일로 주입
```

- `lag_ticks > 0`인 결합은 src별 `deque(maxlen=lag)`에 편차를 밀어 넣고 지연된 값을 사용
- 결합 강도 `gain≈0.3~0.7`이면 윈도우 600샘플에서 r≈0.3~0.7로 관측됨 (노이즈 비율로 조정)

### 4-3. 고장 모드가 결합을 끊도록 수정

`_apply_anomaly`만으로는 상관 붕괴가 안 일어난다 (이상값을 더해도 결합은 살아 있음).
**고장 시나리오가 해당 결합의 `gain`을 일시적으로 변조**하도록 `ActiveAnomaly`에 효과 추가:

| 기존 AnomalyType | 추가 효과 |
|---|---|
| `THICKNESS_DRIFT` (갭 마모) | viscosity→thickness 결합 gain을 0.6→0.1로 (상관 붕괴) |
| `VISCOSITY_RISE` (슬러리 열화) | 점도 자체 상승 + viscosity→thickness gain을 0.6→0.9로 (상관 강화) |
| `PRESSURE_OSC` (베어링 마모) | roll_pressure 진동 + pressure→density 결합에 진동이 전달 안 되도록 gain 0.7→0.2 |
| `TEMP_DEVIATION` (히터 불량) | temp→thickness 결합 부호 반전 (-0.3→+0.3) — 제어계 역작용 시뮬레이션 |

이렇게 하면 "고장 → 물리적 관계 변화 → 상관 변화 → Layer 4 탐지"라는 인과 사슬이 데이터에 실제로 존재하게 된다. 포트폴리오 설명에서도 이 사슬이 핵심 서사가 된다.

---

## 5. SignatureEngine 상세 설계

### 5-1. 파일 구조

```
backend/app/services/signature_engine.py   # 엔진 본체 (신규)
backend/app/services/failure_rules.py      # 시그니처 규칙 테이블 (신규, 순수 데이터)
backend/app/models/alert.py                # FailureAlert ORM (신규)
backend/app/routers/alerts.py              # REST: 알림 목록/확인 처리 (신규)
backend/app/routers/ws.py                  # /ws/alerts 엔드포인트 추가
backend/app/services/anomaly_engine.py     # Layer 4 호출 1줄 추가
backend/app/services/simulator.py          # 인과 결합 (섹션 4)
```

### 5-2. 데이터 구조

```python
WINDOW_TICKS = 600          # 5분 @ 0.5s — 상관 계산 윈도우
EVAL_EVERY_TICKS = 60       # 30초마다 규칙 평가
BASELINE_ALPHA = 0.02       # 베이스라인 EWMA 갱신 계수 (시정수 ≈ 25분)

class RollingWindow:
    """line별 (station, param) → deque[float]. 틱마다 append."""
    buf: dict[tuple[int, str, str], deque[float]]   # maxlen=WINDOW_TICKS

class BaselineStore:
    """페어별 정상 상관 / 파라미터별 정상 분산의 EWMA.
    Redis hash 'sig:baseline:{line_id}'에 주기 저장 → 재시작 시 복원."""
    corr: dict[PairKey, float]      # r_baseline
    std: dict[ParamKey, float]      # std_baseline
```

### 5-3. 규칙 테이블 (`failure_rules.py`)

`prompts.py`의 지식베이스 표를 코드로 옮긴 것. **순수 데이터 선언**으로 유지해 규칙 추가가 코드 수정 없이 가능하도록.

```python
@dataclass(frozen=True)
class AtomCond:
    kind: str                 # CORR_BREAK | CORR_FLIP | CORR_EMERGE | TREND_UP | TREND_DOWN | VAR_SPIKE | OSC
    target: tuple             # 페어 ((sta,par),(sta,par)) 또는 단일 (sta,par)
    # kind별 보조 임계 (기본값은 섹션 2 표)

@dataclass(frozen=True)
class FailureSignature:
    id: str                   # "BEARING_WEAR"
    name_ko: str              # "캘린더 롤 베어링 마모 의심"
    severity: str             # WARNING | CRITICAL
    conditions: list[AtomCond]          # AND 결합
    min_conditions: int | None = None   # None=전부 필요, n이면 n개 이상 (부분 매칭)
    action_ko: str            # 권장 조치
    related_equipment_station: str      # equipment 테이블 연결용

FAILURE_SIGNATURES = [
    FailureSignature(
        id="BEARING_WEAR", name_ko="캘린더 롤 베어링 마모 의심", severity="CRITICAL",
        conditions=[
            AtomCond("OSC", ("calendering", "roll_pressure")),
            AtomCond("CORR_BREAK", (("calendering","roll_pressure"), ("calendering","electrode_density"))),
        ],
        action_ko="롤 베어링 진동 측정 및 윤활 상태 점검, 교체 일정 수립",
        related_equipment_station="calendering",
    ),
    FailureSignature(
        id="GAP_WEAR", name_ko="코팅 다이 갭 마모 의심", severity="WARNING",
        conditions=[
            AtomCond("CORR_BREAK", (("coating","slurry_viscosity"), ("coating","coating_thickness"))),
            AtomCond("TREND_UP", ("coating", "coating_thickness")),
        ],
        action_ko="다이 갭 측정 및 재조정, 두께 프로파일 확인",
        related_equipment_station="coating",
    ),
    FailureSignature(
        id="SLURRY_DEGRADE", name_ko="슬러리 경시 열화 의심", severity="WARNING",
        conditions=[
            AtomCond("TREND_UP", ("coating", "slurry_viscosity")),
            AtomCond("CORR_EMERGE", (("coating","slurry_viscosity"), ("coating","coating_weight"))),
        ],
        min_conditions=1,   # 추세만으로도 1차 경보 (신뢰도 하향)
        action_ko="슬러리 교반 강화, 온도 확인, 잔여 사용 기한 검토",
        related_equipment_station="coating",
    ),
    FailureSignature(
        id="HEATER_FAULT", name_ko="건조로 히터 제어 이상 의심", severity="CRITICAL",
        conditions=[
            AtomCond("VAR_SPIKE", ("coating", "dry_temp_zone2")),
            AtomCond("CORR_FLIP", (("coating","dry_temp_zone2"), ("coating","coating_thickness"))),
        ],
        action_ko="히터 SCR/열전대 점검, 건조 조건 재설정",
        related_equipment_station="coating",
    ),
]
```

**신뢰도 산출** (결정론적, 학습 없음):

```
confidence = 충족 조건들의 정규화 강도 평균
  CORR_*  강도 = |Δr| 를 [임계, 1.0] 구간에서 0~1로 정규화
  TREND   강도 = |slope| / 임계slope, 1.0 캡
  VAR     강도 = (std_now/std_base − 1) / (m − 1), 1.0 캡
부분 매칭(min_conditions) 시 confidence × (충족수/전체수) 패널티
```

### 5-4. 평가 루프

```python
# anomaly_engine._process_batch() 끝에 추가:
self._signature.ingest(readings)              # O(파라미터 수) — deque append만
if self._signature.should_eval():             # 60틱마다
    alerts = self._signature.evaluate()       # 상관 계산 + 규칙 매칭
    await self._signature.persist_and_publish(alerts)
```

`evaluate()` 내부 순서:

1. **활성 페어 추출** — 규칙 테이블에 등장하는 페어만 계산 (전체 조합 아님). 현재 규칙 기준 라인당 ~6페어 × `np.corrcoef` 600샘플 → 1ms 미만.
2. **원자 조건 판정** — 섹션 2의 정의대로. 샘플 수 < 300이면 해당 페어 skip (워밍업).
3. **베이스라인 갱신** — *알림이 하나도 안 뜬 평가 주기에만* `r_base = (1−α)·r_base + α·r_now`로 갱신. 이상 중에 갱신하면 베이스라인이 오염된다 (자기 면역 원칙). std_baseline도 동일.
4. **시그니처 매칭 + 신뢰도 계산**
5. **AlertGate 통과** (섹션 6)

### 5-5. 알림 페이로드

```json
{
  "type": "failure_alert",
  "alert_id": 42,
  "signature_id": "BEARING_WEAR",
  "name": "캘린더 롤 베어링 마모 의심",
  "severity": "CRITICAL",
  "state": "RAISED",
  "line_id": 1,
  "confidence": 0.78,
  "detected_at": "2026-06-10T12:34:56Z",
  "evidence": [
    {"kind": "OSC", "param": "calendering.roll_pressure", "detail": "lag=14틱 자기상관 r=0.71"},
    {"kind": "CORR_BREAK", "pair": "roll_pressure↔electrode_density",
     "r_baseline": 0.68, "r_now": 0.12, "delta": -0.56}
  ],
  "action": "롤 베어링 진동 측정 및 윤활 상태 점검, 교체 일정 수립",
  "equipment_ids": [3]
}
```

`evidence`가 핵심이다 — 수치 근거가 페이로드에 들어 있으므로 프론트가 LLM 없이 "왜"를 보여줄 수 있고, 나중에 LLM 상세 분석을 붙일 때 이 JSON을 그대로 컨텍스트로 넘기면 된다.

---

## 6. AlertGate: 중복 억제 상태머신

상관 패턴 이상은 수 분간 지속되므로 cooldown만으로는 부족하다. 알림에 생애주기를 부여한다:

```
                evaluate()에서 매칭        N회 연속 미매칭(기본 4회=2분)
   (없음) ────────────────────▶ RAISED ──▶ ACTIVE ─────────────────────▶ RESOLVED
                                  │           │
                                  │           └─ 재평가마다 confidence/evidence 갱신
                                  │              (UPDATE 발행, 새 토스트 X)
                                  └─ WebSocket "RAISED" 발행 (토스트 1회)
```

- 키: `(line_id, signature_id)`
- **RAISED**: 신규 매칭. DB insert + `alert:live` 발행 → 프론트 토스트
- **ACTIVE**: 같은 키가 계속 매칭. DB update(last_seen, confidence) + state="UPDATED" 발행 → 프론트는 배너 수치만 갱신, 토스트 없음
- **RESOLVED**: 연속 N회 미매칭. DB에 resolved_at 기록 + "RESOLVED" 발행 → 프론트 배너 제거 + "해소됨" 토스트
- RESOLVED 후 `REARM_COOLDOWN`(기본 5분) 동안 동일 키 재발생 시 RAISED가 아닌 ACTIVE 복귀 (플래핑 방지)

이 상태머신 덕에 **하나의 고장 = 하나의 알림 레코드**가 보장된다 (기존 anomaly_events의 틱당 중복 문제와 대비되는 어필 포인트).

---

## 7. 콜드스타트 / 베이스라인 전략

| 상황 | 동작 |
|---|---|
| 엔진 기동 직후 | Redis `sig:baseline:{line}`에서 복원 시도. 없으면 워밍업 모드 |
| 워밍업 (샘플 < 300) | 원자 조건 평가 skip, 베이스라인만 축적. 대시보드에 "학습 중" 표시용 상태 노출 (`GET /api/alerts/engine-status`) |
| 베이스라인 자체가 비정상일 위험 | 워밍업 중 Layer 1~2 이벤트가 발생한 파라미터는 베이스라인 축적에서 제외 |
| 운전 조건 변경 (라인 속도 변경 등) | EWMA(α=0.02)가 ~25분에 걸쳐 자연 적응. 급격한 레시피 변경은 수동 리셋 API (`POST /api/alerts/baseline/reset`) |

---

## 8. 저장소 / API / 프론트

### 8-1. DB 모델 (`models/alert.py`)

```python
class FailureAlert(Base):
    __tablename__ = "failure_alerts"
    id:            Mapped[int]           # PK
    signature_id:  Mapped[str]           # "BEARING_WEAR"
    line_id:       Mapped[int]
    severity:      Mapped[str]
    confidence:    Mapped[float]
    state:         Mapped[str]           # RAISED | ACTIVE | RESOLVED
    evidence:      Mapped[str]           # JSON (Text)
    raised_at:     Mapped[datetime]
    last_seen_at:  Mapped[datetime]
    resolved_at:   Mapped[datetime | None]
    acked_by:      Mapped[str | None]    # 운전원 확인 (향후 인증 연동)
    acked_at:      Mapped[datetime | None]
```

### 8-2. REST (`routers/alerts.py`)

```
GET  /api/alerts                  ?state=&line_id=&hours=   목록
GET  /api/alerts/active           현재 ACTIVE/RAISED만 (대시보드 배너 초기 로드)
POST /api/alerts/{id}/ack         운전원 확인 처리
GET  /api/alerts/engine-status    워밍업/베이스라인 상태
POST /api/alerts/baseline/reset   베이스라인 수동 리셋
```

### 8-3. WebSocket

`ws.py`에 `/ws/alerts` 추가 — 기존 `/ws/live`와 동일 패턴으로 `alert:live` 구독. (`/ws/live`에 합치지 않는 이유: 센서 스트림은 0.5초 주기 고빈도라 알림만 필요한 컴포넌트가 불필요한 메시지를 다 받게 됨.)

### 8-4. 프론트

```
src/hooks/useAlerts.ts            /ws/alerts 구독 + /api/alerts/active 초기 로드, zustand store
src/components/Alerts/AlertToast.tsx    RAISED/RESOLVED 시 토스트 (CRITICAL은 수동 닫기)
src/components/Alerts/AlertBanner.tsx   ACTIVE 알림 상단 고정 배너: 이름·신뢰도·경과시간·[확인][상세]
src/components/Alerts/AlertDetail.tsx   evidence 시각화: Δr 게이지, 해당 페어 산점도(전/후 비교)
```

- 상세 패널의 **"산점도 전/후 비교"**(베이스라인 기간 vs 최근 5분)가 상관 붕괴를 한눈에 보여주는 킬러 비주얼 — `GET /api/process/history` 재사용으로 구현 가능
- 상세 패널 하단에 "AI 상세 분석 요청" 버튼 → 기존 AgentChat에 evidence JSON을 프롬프트로 주입 (LLM은 여기서만, 온디맨드)

---

## 9. 구현 순서 (의존성 순)

| 단계 | 작업 | 비고 |
|---|---|---|
| 1 | 시뮬레이터 인과 결합 + 고장 시 gain 변조 (섹션 4) | 이게 없으면 이후 전부 검증 불가 |
| 2 | `/api/correlation` 기존 엔드포인트로 정상 상관이 실제 관측되는지 수동 검증 | r≈0.3~0.7 확인 |
| 3 | `failure_rules.py` + `signature_engine.py` (원자 조건, 베이스라인, 신뢰도) | 순수 로직 — **pytest 필수** (합성 시계열로 CORR_BREAK 등 단위 검증) |
| 4 | AlertGate 상태머신 + `failure_alerts` 모델 + anomaly_engine 통합 | |
| 5 | `alert:live` 발행 + `/ws/alerts` + REST | |
| 6 | 프론트 useAlerts/Toast/Banner | |
| 7 | E2E 데모 시나리오: `POST /simulator/inject?anomaly_type=PRESSURE_OSC` → 30~60초 내 BEARING_WEAR 알림 → 5분 후 RESOLVED | 면접 시연 스크립트 |
| 8 | (선택) 상세 패널 산점도 + LLM 온디맨드 분석 연결 | |

### 검증 기준 (단계 7)
- 주입 → RAISED까지 지연 ≤ 평가주기 2회 (60초)
- 정상 운전 1시간 동안 오탐 0건 (random inject 끄고 측정 — `ANOMALY_INJECT_PROB=0`)
- 같은 고장 지속 중 토스트 정확히 1회

---

## 10. 튜닝 파라미터 요약 (config로 노출 권장)

| 파라미터 | 기본값 | 효과 |
|---|---|---|
| `WINDOW_TICKS` | 600 (5분) | 짧으면 민감/불안정, 길면 둔감/안정 |
| `EVAL_EVERY_TICKS` | 60 (30초) | 알림 지연 vs 연산 빈도 |
| `BASELINE_ALPHA` | 0.02 | 운전 조건 변화 적응 속도 |
| `CORR_BREAK` 임계 | base≥0.5 → now<0.3 | 민감도 핵심 노브 |
| `RESOLVE_MISSES` | 4회 (2분) | 해소 판정 속도 |
| `REARM_COOLDOWN` | 5분 | 플래핑 억제 |

---

## 부록: 왜 LLM 없이가 맞는가 (포트폴리오 설명용 논거)

1. **지연시간** — 규칙 평가는 ms 단위, LLM은 수 초 + 큐잉. 실시간 알림 경로에 LLM이 끼면 SLA를 못 건다.
2. **비용** — 30초마다 2개 라인 평가 = 일 5,760회. LLM이면 호출당 비용 × 5,760/일.
3. **결정론** — 같은 데이터에 같은 판정. 제조 현장에서 "어제는 울렸는데 오늘은 안 울림"은 신뢰 상실.
4. **검증 가능성** — 규칙은 단위 테스트로 회귀 검증 가능. LLM 판정은 eval 셋 없이는 검증 불가.
5. **역할 분리** — 탐지(결정론적 규칙) / 설명·종합(LLM 온디맨드). 각자 잘하는 것만 시키는 구조 자체가 에이전틱 시스템 설계 역량의 증거.
