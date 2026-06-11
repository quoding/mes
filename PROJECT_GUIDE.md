# PNT Smart Factory MES — 프로젝트 이해 가이드

이 문서는 "어떤 기술로, 왜 이렇게 만들었는지", "코드 안의 핵심 요소(변수/클래스/함수)는 무엇인지", "도메인(롤투롤 2차전지 전극 제조공정) 지식은 무엇인지"를 한 번에 정리한 학습용 자료입니다. 면접/자소서에서 프로젝트를 설명할 때 이 문서를 기준으로 답변을 준비하면 됩니다.

---

# 1. 전체 아키텍처 한눈에 보기

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Docker Compose (4 컨테이너)                    │
│                                                                          │
│  ┌────────────┐   ┌──────────────────┐   ┌───────────┐  ┌──────────┐ │
│  │ pnt-frontend│  │   pnt-backend     │  │pnt-postgres│  │ pnt-redis│ │
│  │ React+Vite  │◄─┤ FastAPI           │◄─┤ Timescale  │  │  Redis7  │ │
│  │ :5173       │  │ :8000             │  │ DB :5432   │  │  :6379   │ │
│  └────────────┘   └──────────────────┘   └───────────┘  └──────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

- **pnt-postgres**: `timescale/timescaledb:latest-pg16` — PostgreSQL 16 + TimescaleDB 확장. 시계열 데이터(`process_data`)를 hypertable로 저장.
- **pnt-redis**: `redis:7-alpine` — Pub/Sub(실시간 데이터 브로드캐스트), 대화 메모리, rate limiting, Layer4 baseline 영속화에 사용.
- **pnt-backend**: FastAPI 앱. 시뮬레이터 → 이상탐지 엔진 → LLM 에이전트 → REST/WS API 전부 포함.
- **pnt-frontend**: React 19 + Vite 개발 서버. 대시보드 UI + AI 챗봇 UI.

### 데이터 흐름 (한 틱의 여정)

```
ProcessSimulator (0.5초마다)
   │  센서값 생성 (정상분포 + 드리프트 + 이상 주입 + 인과결합)
   ├─► PostgreSQL INSERT (process_data 테이블, TimescaleDB hypertable)
   └─► Redis PUBLISH "process:live"
         │
         ├─► AnomalyEngine (Layer1 Z-score, Layer2 EWMA, Layer3 IsolationForest)
         │     └─► 이상 발견 시 anomaly_events 테이블 저장 + Redis "anomaly:live" 발행
         │
         ├─► SignatureEngine (Layer4, 30초마다 평가)
         │     └─► 고장 전조 패턴 매칭 시 failure_alerts 테이블 저장 + Redis "alert:live" 발행
         │
         └─► WebSocket (/ws/live) 구독자(브라우저)에게 실시간 브로드캐스트
                │
                ▼
         React 프론트엔드 (processStore, alertStore) → Recharts 차트 갱신
```

사용자가 AI 챗봇에 질문하면, Pydantic AI 에이전트가 `MES_TOOLS`(DB/Redis 조회 함수)를 호출해서 실제 데이터를 가져온 뒤 SSE 스트리밍으로 답변을 생성합니다.

---

# 2. 백엔드 기술 스택

| 분류 | 기술 | 이 프로젝트에서의 역할 |
|---|---|---|
| 웹 프레임워크 | **FastAPI** | REST API, WebSocket, SSE 스트리밍 서버 |
| 비동기 ORM | **SQLAlchemy 2.0 (async)** | PostgreSQL 모델 정의 및 비동기 쿼리 |
| DB | **PostgreSQL 16 + TimescaleDB** | `process_data`를 hypertable로 만들어 대용량 시계열 데이터를 효율적으로 저장/조회, retention policy로 오래된 데이터 자동 삭제 |
| 캐시/메시징 | **Redis 7** | Pub/Sub(`process:live`, `anomaly:live`, `alert:live`), 대화 이력 저장, IP rate limiting, Layer4 baseline 저장 |
| LLM 에이전트 | **Pydantic AI** | OpenAI 모델을 함수 호출(tool calling) 기반 에이전트로 감싸는 프레임워크. `Agent`, `RunContext`, `mes_agent.tool()` 사용 |
| LLM | **OpenAI gpt-5.4-nano / gpt-5.4-mini** | nano: 빠르고 단순한 질의, mini: 복잡한 분석/리포트 생성 (자동 라우팅) |
| 수치 분석 | **NumPy, SciPy(stats.pearsonr)** | 평균/표준편차/추세(기울기)/자기상관/피어슨 상관계수 계산 |
| 머신러닝 | **scikit-learn (IsolationForest)** | 다변량 이상치 탐지 (배치) |
| 마이그레이션 | **Alembic** | DB 스키마 버전 관리 |
| 컨테이너 | **Docker Compose** | 4개 서비스 오케스트레이션 |

---

# 3. 프론트엔드 기술 스택

| 분류 | 기술 | 역할 |
|---|---|---|
| UI 프레임워크 | **React 19 + TypeScript** | 컴포넌트 기반 SPA |
| 빌드 도구 | **Vite** | 개발 서버(HMR), 번들링 |
| 상태관리 | **Zustand v5** | `processStore`(실시간 데이터), `alertStore`(고장 전조 알림) |
| 서버 상태 | **TanStack Query (react-query)** | REST API 데이터 페칭 + 자동 polling(`refetchInterval`) |
| 스타일 | **TailwindCSS v4** | 유틸리티 클래스 기반 다크 테마 디자인 |
| 차트 | **Recharts** | 실시간 라인차트, 상관관계 히트맵 |
| 마크다운 렌더링 | **react-markdown** | AI 챗봇 응답의 `**굵게**`, `## 제목`, 리스트 등을 실제 서식으로 렌더링 |
| 아이콘 | **lucide-react** | UI 아이콘 |
| 실시간 통신 | **WebSocket (useWebSocket)**, **SSE (useMesAgent, EventSource 패턴)** | 센서 데이터 실시간 수신 / 챗봇 스트리밍 응답 수신 |

---

# 4. 백엔드 코드 구조 상세

```
backend/app/
├── core/
│   ├── config.py       # 환경설정 (Settings, Pydantic BaseSettings)
│   ├── database.py     # SQLAlchemy 엔진/세션, hypertable 초기화
│   └── redis.py        # Redis connection pool
├── models/
│   ├── process.py      # ProcessData (hypertable)
│   ├── anomaly.py       # AnomalyEvent
│   ├── equipment.py     # Equipment, MaintenanceReport
│   └── alert.py         # FailureAlert (Layer4)
├── agents/
│   ├── mes_agent.py     # Pydantic AI Agent 정의
│   ├── tools.py         # 에이전트가 호출하는 도구 7종
│   ├── prompts.py        # MES_SYSTEM_PROMPT (도메인 지식 통째로 들어있음)
│   ├── deps.py           # MesDeps (redis, db, simulator 묶음)
│   └── routing.py        # nano/mini 모델 자동 선택 로직
├── services/
│   ├── simulator.py       # 롤투롤 공정 데이터 시뮬레이터 (가장 핵심)
│   ├── anomaly_engine.py  # Layer 1~3 이상탐지
│   ├── signature_engine.py# Layer 4 고장 전조 신호 탐지
│   ├── failure_rules.py   # Layer 4 규칙 테이블 (선언적 데이터)
│   ├── correlation.py     # 상관관계 분석 (에이전트 도구용)
│   ├── predictive.py       # RAG-like 예지보전
│   └── memory.py            # Redis 기반 대화 이력
└── routers/
    ├── agent.py    # /agent — SSE 챗봇 엔드포인트
    ├── process.py  # /process — 시계열 데이터, 시뮬레이터 시작/정지
    ├── anomaly.py  # /anomaly — 이상 이력/요약
    ├── correlation.py # /correlation — 상관관계 API
    ├── maintenance.py # /maintenance — 예지보전 API
    ├── alerts.py   # /alerts — Layer4 알림 API
    ├── ws.py       # /ws/live — 실시간 WebSocket
    └── health.py   # /health — 헬스체크
```

## 4.1 `core/config.py` — 환경설정

- `Settings(BaseSettings)` 클래스: Pydantic이 환경변수를 자동으로 읽어 타입 검증.
- 주요 필드:
  - `openai_model_default = "gpt-5.4-nano"`, `openai_model_complex = "gpt-5.4-mini"`
  - `simulator_interval_ms = 500` — 시뮬레이터가 0.5초마다 데이터 생성
  - `anomaly_inject_prob = 0.015` — 매 틱마다 1.5% 확률로 이상 시나리오 자동 주입
  - `redis_ttl_seconds = 86400` — 대화 이력 24시간 후 자동 삭제
  - `_read_secret()`: Docker secrets(`/run/secrets/{name}`)를 우선 읽고 없으면 환경변수 사용 — 운영환경에서 비밀값을 안전하게 주입하는 패턴
  - `database_url`, `redis_url`: `computed_field`로 다른 설정값들을 조합해 자동 생성 (`postgresql+asyncpg://...`)

## 4.2 `services/simulator.py` — 공정 데이터 시뮬레이터 (핵심)

### ParamDef — 파라미터 정의
```python
@dataclass
class ParamDef:
    name: str
    unit: str
    low: float          # 정상 범위 하한
    high: float         # 정상 범위 상한
    noise_sigma: float  # 매 틱 가우시안 노이즈 표준편차
    drift_rate: float = 0.0  # 매 틱 서서히 변화하는 양 (설비 마모 시뮬레이션)
```

`STATION_PARAMS: dict[str, list[ParamDef]]` — 4개 스테이션 × 라인2개의 모든 파라미터 정의를 담은 딕셔너리. (자세한 값은 7장 도메인 지식 참고)

### Coupling — 인과관계 모델 (이 프로젝트의 차별점)
```python
@dataclass(frozen=True)
class Coupling:
    src: tuple[str, str]   # (station, param) — 원인
    dst: tuple[str, str]   # (station, param) — 결과
    gain: float            # dst 변화량 = gain × (src 정규화 편차) × dst의 noise_sigma
    lag_ticks: int = 0     # 공정상 물리적 지연(틱 수)
```

`COUPLINGS: list[Coupling]` — "정상 운전 중" 파라미터 간 물리적 인과관계를 인코딩. 예:
- 슬러리 점도↑ → 코팅 두께↑ (gain=0.8, 강한 양의 상관)
- 라인 속도↑ → 코팅 중량↓ (gain=-0.5, 음의 상관)
- 롤 압력↑ → 전극 밀도↑ (gain=0.7)

> gain 값들은 E2E 테스트(`tests/test_e2e_detection.py`)로 검증된 값 — Layer 4가 요구하는
> 베이스라인 상관 강도(예: CORR_FLIP은 |r|≥0.4)를 실제로 만들어내는지 테스트가 보증한다.

이 결합 덕분에 시뮬레이터가 만드는 데이터는 단순 랜덤이 아니라 **실제 공정처럼 변수들끼리 서로 영향을 주고받습니다**. → 이게 있어야 상관관계 분석(`correlation.py`)과 Layer4(`signature_engine.py`)가 의미 있는 결과를 낼 수 있음.

### AnomalyType — 이상 시나리오 5종 (Enum)
```python
class AnomalyType(str, Enum):
    TENSION_SPIKE   = "TENSION_SPIKE"    # 장력 급변 → 주름/파단
    THICKNESS_DRIFT = "THICKNESS_DRIFT"  # 코팅 두께 점진 이탈
    TEMP_DEVIATION  = "TEMP_DEVIATION"   # 건조 온도 급변
    VISCOSITY_RISE  = "VISCOSITY_RISE"   # 슬러리 점도 상승
    PRESSURE_OSC    = "PRESSURE_OSC"     # 롤 압력 주기 진동 (베어링 마모)
```

### COUPLING_GAIN_OVERRIDES — "고장 → 관계 변화" 시뮬레이션 (가장 정교한 부분)
이상 시나리오가 활성화되면 단순히 해당 파라미터 값만 튀는 게 아니라, **변수 간 상관관계(gain) 자체가 변조**됩니다.

| 이상 유형 | 변조되는 결합 | 의미 |
|---|---|---|
| `THICKNESS_DRIFT` | 점도→두께 gain 0.8 → 0.1 | 다이 갭 마모로 정상적 인과관계가 붕괴(상관 약화) |
| `VISCOSITY_RISE` | 점도→두께 gain 0.8 → 0.9 | 슬러리 열화로 상관관계가 비정상적으로 강화 |
| `PRESSURE_OSC` | 압력→밀도 gain 0.7 → 0.0 | 베어링 마모로 압력 진동이 밀도에 전달 안 됨 (상관 붕괴) |
| `TEMP_DEVIATION` | 온도→두께 gain -0.6 → +0.6 | 히터 제어계 이상으로 인과관계 부호 반전 |

→ 이게 바로 **Layer4(SignatureEngine)가 탐지하는 대상**입니다. "값이 이상한가"가 아니라 "**변수 간 관계가 평소와 달라졌는가**"를 보는 것.

### ActiveAnomaly — 현재 진행 중인 이상 상태
```python
@dataclass
class ActiveAnomaly:
    anomaly_type: AnomalyType
    line_id: int
    station: str
    param: str
    ticks_remaining: int   # 남은 지속 시간(틱)
    magnitude: float = 1.0 # 이상 강도
    phase: float = 0.0     # 진동(OSC) 시나리오의 위상
```

## 4.3 `services/anomaly_engine.py` — Layer 1~3 이상탐지

### `_ParamState` — 파라미터별 롤링 상태
- `buf: deque(maxlen=50)` — 최근 50개 값 (Z-score용)
- `ewma`, `ewma_var` — EWMA 평균/분산 (제어차트용)

**Layer 1 (Z-score)**: 최근 50틱 평균/표준편차 기준 `|z| = |value - mean| / std`
- `z > 4.0` → CRITICAL, `z > 3.0` → WARNING

**Layer 2 (EWMA 제어차트)**: `EWMA_LAMBDA=0.2`로 지수가중이동평균과 분산을 온라인 갱신.
- `ucl/lcl = center ± 3σ_ewma` 를 벗어나면 WARNING. Z-score보다 **느린 드리프트**를 잘 잡음.

**임계값(threshold) 체크**: `value > high*1.05` 또는 `< low*0.95` → WARNING/CRITICAL (정상범위 ±5%/±15% 기준)

### `AnomalyEngine` 클래스
- `_states: dict[line][station][param] → _ParamState` — 모든 파라미터의 상태를 메모리에 보관
- `_if_buffers`, `IF_BATCH_TICKS=600` (=5분) — Isolation Forest용 벡터 누적
- `_last_event_time` + `EVENT_COOLDOWN_SECONDS=60` — 같은 (라인,스테이션,파라미터,패턴) 조합은 60초 내 중복 기록 방지 (이벤트 폭주 방지)

**Layer 3 (Isolation Forest)**: 5분마다 스테이션별로 모든 파라미터를 벡터화해 `IsolationForest(contamination=0.05)`로 학습+예측. 최근 20틱 중 40% 이상이 이상치(-1)면 `LAYER3_ISOLATION_FOREST` 이벤트 발행.

`run()`: Redis `process:live` 채널을 구독하는 무한 루프. 매 틱마다 `_process_batch()` 실행 후 결과를 `anomaly_events` 테이블에 저장하고 `anomaly:live`로 발행. 동시에 `signature_engine.ingest()`도 호출.

## 4.4 `services/signature_engine.py` + `failure_rules.py` — Layer 4 (이 프로젝트의 핵심 차별점)

> Layer 1~3은 "이 **값**이 이상한가?"를 묻는다면, Layer 4는 "이 **관계**가 이상한가?"를 묻습니다.

### 핵심 개념
1. 모든 관련 파라미터의 최근 5분(`WINDOW_TICKS=600`) 데이터를 deque에 보관
2. 30초마다(`EVAL_EVERY_TICKS=60`) "베이스라인"(평소의 상관계수/표준편차)과 "현재값"을 비교
3. 차이가 크면 "atom condition"이 발생했다고 판단
4. `FAILURE_SIGNATURES`에 정의된 규칙과 매칭되면 알림(AlertGate) 발생

### Atom Conditions (7종)
| 종류 | 의미 | 판정 기준 |
|---|---|---|
| `CORR_BREAK` | 상관관계 붕괴 | `|r_baseline| ≥ 0.5` 였는데 `|r_now| < 0.3` |
| `CORR_FLIP` | 상관관계 부호 반전 | `r_base * r_now < 0` 이고 둘 다 `|r| ≥ 0.4` |
| `CORR_EMERGE` | 새로운 상관관계 출현 | `|r_base| < 0.3` 였는데 `|r_now| ≥ 0.6` |
| `TREND_UP/DOWN` | 추세(선형회귀 기울기) | `|slope| > 1 × (high-low)/WINDOW_TICKS` |
| `VAR_SPIKE` | 분산 급증 | `std_now > 2.5 × std_baseline` |
| `OSC` | 주기적 진동 | 자기상관(lag 10~95) `|r| ≥ 0.6` |

### 베이스라인 자기-면역(self-immune) 갱신
```python
if not atoms:  # 이번 평가에서 아무 이상도 안 잡혔을 때만
    baseline = (1-α) * baseline + α * current   # α=0.02, 시정수 ≈ 25분
```
→ 이상이 감지되는 동안은 베이스라인을 갱신하지 않음으로써, "고장 상태"가 새로운 "정상"으로 학습되는 것을 방지.

### `FAILURE_SIGNATURES` (4가지 고장 시그니처, `failure_rules.py`)
| ID | 이름 | 조건 (AND) | 심각도 |
|---|---|---|---|
| `BEARING_WEAR` | 캘린더 롤 베어링 마모 의심 | OSC(roll_pressure) + CORR_BREAK(압력↔밀도) | CRITICAL |
| `GAP_WEAR` | 코팅 다이 갭 마모 의심 | CORR_BREAK(점도↔두께) + TREND_UP(두께) | WARNING |
| `SLURRY_DEGRADE` | 슬러리 경시 열화 의심 | TREND_UP(점도) + CORR_EMERGE(점도→두께) — `min_conditions=1`로 1개만 만족해도 신뢰도 낮춰서 1차 경보 | WARNING |
| `HEATER_FAULT` | 건조로 히터 제어 이상 의심 | VAR_SPIKE(온도) + CORR_FLIP(온도↔두께) | CRITICAL |

### AlertGate 상태머신
```
RAISED → ACTIVE → (4회 연속 미매칭, 2분) → RESOLVED → (10회 쿨다운 동안 재발생 시) ACTIVE
```
- 한 번의 진행 중인 고장이 여러 개의 중복 알림을 만들지 않도록 상태를 관리
- `failure_alerts` 테이블에 저장 + Redis `alert:live` 채널로 발행 → 프론트 `AlertBanner`/`AlertToast`가 실시간 수신

### Redis 기반 baseline 영속화
`sig:baseline:{line}` 키에 corr/std 베이스라인을 JSON으로 저장 → 백엔드 재시작해도 학습된 베이스라인 유지(`restore_baselines()`).

## 4.5 `services/correlation.py` — 상관관계 분석 (에이전트 도구용)

- `compute_correlation_matrix(db, line_id, station, window_minutes)`: 한 스테이션 내 모든 파라미터 쌍에 대해 `scipy.stats.pearsonr` 계산, `abs_r` 기준 정렬
- `DOMAIN_PAIRS`: 도메인 지식 기반으로 미리 정의된 "흥미로운" 교차-스테이션 파라미터 쌍 (예: 점도↔두께, 롤압력↔밀도)
- `_interpret(r, p)`: r값을 "매우 강한/강한/중간/약한 양의/음의 상관"으로 한국어 해석 텍스트 생성

## 4.6 `services/predictive.py` — RAG-like 예지보전

벡터DB 없이 통계적 유사도 기반 RAG를 흉내냅니다.

```
1. _extract_features(values) → {mean, std, min, max, skewness, trend_slope}
   (현재 30분 윈도우의 통계적 특징 벡터)
2. _fetch_similar_cases() → 과거 90일 anomaly_events 중 같은 station,
   feature_snapshot이 저장된 이벤트들을 후보로 가져옴
3. _euclidean_distance(현재 features, 과거 features) → 정규화 유클리드 거리
4. 거리순 정렬 후 상위 3개 = "유사 과거 사례"
5. _risk_score(): 가장 가까운 거리를 시그모이드형 함수로 0~90점 변환 + std/trend 기반 보너스(최대10) → 0~100 위험도
6. _generate_llm_report(): 위 컨텍스트를 JSON으로 만들어 gpt-5.4-nano에 전달,
   "[위험도: N/100] 예상 고장 부위 / 근거 / 권장 조치" 형식의 리포트 생성
   (LLM 실패 시 규칙기반 fallback 텍스트로 대체)
7. 결과를 maintenance_reports 테이블에 저장
```

## 4.7 `agents/` — Pydantic AI 에이전트

### `mes_agent.py`
```python
mes_agent: Agent[MesDeps, str] = Agent(
    model="openai:gpt-5.4-nano",
    deps_type=MesDeps,
    system_prompt=MES_SYSTEM_PROMPT,
    retries=1,
    model_settings=ModelSettings(max_tokens=1024),
)
for _tool in MES_TOOLS:
    mes_agent.tool(_tool)
```
- `Agent[MesDeps, str]`: 의존성 타입(MesDeps)과 출력 타입(str)을 제네릭으로 명시 — Pydantic AI의 타입 안전 패턴
- `mes_agent.tool(_tool)`: 함수를 LLM이 호출 가능한 "tool"로 등록. LLM이 함수 시그니처/docstring을 보고 언제 호출할지 스스로 판단(function calling)

### `deps.py` — `MesDeps`
```python
@dataclass
class MesDeps:
    redis: Redis | None
    db: AsyncSession | None
    simulator: ProcessSimulator | None
```
도구 함수들이 `RunContext[MesDeps]`를 통해 DB/Redis/시뮬레이터에 접근.

### `routing.py` — nano/mini 자동 선택
```python
_COMPLEX_MARKERS = ("분석","비교","요약","원인","보고서","예측","상관","이상","explain","analyze","report","predict")
_COMPLEX_THRESHOLD_CHARS = 150
_COMPLEX_MARKER_HITS = 2

def select_model_id(message: str) -> str:
    # 메시지 길이 > 150자 OR 복잡도 키워드 2개 이상 매치 → gpt-5.4-mini
    # 그 외 → gpt-5.4-nano
```
→ "지난 24시간 이상 이력 요약해줘"처럼 분석/요약을 요구하는 질문은 mini, "안녕"같은 단순 질문은 nano로 비용 최적화.

### `tools.py` — MES_TOOLS (7개 도구)

| 도구 함수 | 역할 | 핵심 로직 |
|---|---|---|
| `query_process_data(line_id, station, param, minutes=30)` | 시계열 데이터 조회 | DB에서 최근 N분 데이터 조회 → 평균/표준편차/min/max/현재값 계산, 정상범위(STATION_PARAMS)와 비교해 "정상/주의/위험" 판정 |
| `get_anomaly_history(line_id?, severity?, hours=24)` | 이상 이력 조회 | `anomaly_events`에서 필터링, severity별 건수 집계, 최근 10건 상세 출력 |
| `analyze_correlation(line_id, station, window_minutes=30)` | 상관관계 분석 | `compute_correlation_matrix` 호출, `|r|≥0.6 & p<0.05`인 "강한 상관" 쌍 강조 |
| `get_equipment_status(equipment_id)` | 설비 상태/정비 이력 | 누적가동시간, 마지막/다음 정비일, 정비 임박도(🔴/🟠/🟡/✅) |
| `predict_failure_risk(equipment_id)` | 예지보전 리포트 | `predict_maintenance()` 호출, LLM 요약 반환 |
| `generate_shift_report(line_id, hours=8)` | 교대 보고서 | severity별 이상 건수 집계 + Redis에서 주요 파라미터 현재값 조회 → 상태 요약(✅/⚠️/🔴) |
| `inject_test_anomaly(anomaly_type, line_id=1)` | 테스트용 이상 주입 | 시뮬레이터의 `inject_anomaly()` 직접 호출 (데모/시연용) |

`MES_TOOLS = (query_process_data, get_anomaly_history, analyze_correlation, get_equipment_status, predict_failure_risk, generate_shift_report, inject_test_anomaly)`

### `prompts.py` — `MES_SYSTEM_PROMPT`
도메인 지식(7장 참고)을 통째로 시스템 프롬프트에 포함 — 4개 스테이션의 파라미터 정상범위 + 5가지 이상 패턴(원인/관련변수/조치)을 표로 제공. 응답 원칙: 한국어, 수치 근거 명시, 조치 권고 포함, 심각도 표시, 간결성.

## 4.8 `services/memory.py` — 대화 메모리

- `redis_append_conversation(redis, session_id, role, content)`: `mes:conv:{session_id}` 리스트에 RPUSH 후 `redis_ttl_seconds(24h)`로 TTL 갱신
- `redis_get_conversation()`: LRANGE로 전체 이력 조회
- `to_message_history(turns)`: 저장된 turn들을 Pydantic AI의 `ModelRequest`/`ModelResponse` 객체로 변환 — 에이전트가 이전 대화 맥락을 이어받을 수 있게 함
- 세션ID는 프론트엔드 `useRef`에만 보관 (localStorage 미사용) → 새로고침하면 새 세션 시작

---

# 5. 프론트엔드 코드 구조 상세

```
frontend/src/
├── pages/
│   ├── DashboardPage.tsx   # 메인 대시보드 (KPI + 차트 + 알림 + 챗봇 + 히트맵)
│   ├── ProcessPage.tsx     # 공정별 상세 페이지
│   ├── AnomalyPage.tsx     # 이상 이력 페이지
│   ├── MaintenancePage.tsx # 예지보전 페이지
│   └── AgentPage.tsx       # 챗봇 전용 페이지
├── components/
│   ├── Dashboard/KpiCard.tsx       # KPI 카드 (가동상태/이상건수 등)
│   ├── ProcessLine/RealtimeChart.tsx # Recharts 실시간 라인차트 + 임계선
│   ├── AnomalyPanel/AnomalyList.tsx  # 이상 이벤트 리스트
│   ├── CorrelationMap/HeatMap.tsx    # 상관관계 히트맵
│   ├── PredictiveMaint/RiskCard.tsx  # 예지보전 위험도 카드
│   ├── AgentChat/AgentChat.tsx       # AI 챗봇 UI (SSE + react-markdown)
│   └── Alerts/AlertBanner.tsx, AlertToast.tsx # Layer4 알림 UI
├── hooks/
│   ├── useWebSocket.ts  # /ws/live 구독, processStore 업데이트
│   ├── useAlerts.ts     # alert:live 구독, alertStore 업데이트
│   └── useMesAgent.ts   # SSE 챗봇 통신
├── stores/
│   ├── processStore.ts  # 실시간 센서값 + 롤링 버퍼 + 이상이벤트 (Zustand)
│   └── alertStore.ts    # Layer4 알림 상태 (Zustand)
├── types/mes.ts          # 모든 TypeScript 인터페이스
└── lib/api.ts            # axios 인스턴스
```

## 5.1 `stores/processStore.ts`
```typescript
interface ProcessState {
  latest: Record<string, {value:number, unit:string, time:string}>; // "line:station:param" 키
  buffers: ParamBuffer;          // 차트용 최근 200개 롤링 버퍼
  liveAnomalies: AnomalyEvent[]; // 최근 50개
  wsStatus: "connecting"|"connected"|"disconnected";
  updateReadings, addAnomalies, setWsStatus
}
```
- `BUFFER_SIZE = 200`: 차트가 보여줄 최대 데이터 포인트 수 (200 × 0.5초 = 100초 분량)
- key 포맷 `"${line_id}:${station}:${param}"` — 백엔드와 동일한 식별자 패턴 사용

## 5.2 `types/mes.ts` — 핵심 타입
- `ProcessReading`: WebSocket으로 오는 센서 한 틱 데이터
- `AnomalyEvent`: Layer1~3 이상 이벤트 (severity: INFO/WARNING/CRITICAL)
- `FailureAlert` / `FailureAlertWsMessage`: Layer4 고장 전조 알림 (state: RAISED/ACTIVE/UPDATED/RESOLVED, evidence 배열 포함)
- `Equipment`, `MaintenanceReport`, `CorrelationPair`

## 5.3 `DashboardPage.tsx` — 메인 화면 구성
- `useWebSocket()`, `useAlerts()` 훅으로 실시간 구독 시작
- TanStack Query로 시뮬레이터 상태(`/process/simulator/status`, 5초마다), 이상 요약(`/anomaly/summary`, 30초), 이상 이벤트(`/anomaly/events`, 15초) polling
- 시뮬레이터 시작/정지 토글 버튼
- 레이아웃: KPI 카드 4개 → Layer4 알림 배너 → Line1 코팅 실시간 차트 6개 → (이상이력 / 상관히트맵 / AI챗봇) 3분할

## 5.4 `AgentChat.tsx` + `useMesAgent.ts`
- SSE로 토큰 단위 스트리밍 응답 수신, `streaming: true`인 동안 커서 깜빡임 효과
- `react-markdown`으로 LLM 응답을 실제 마크다운 서식(굵게, 제목, 리스트, 표, 코드블럭)으로 렌더링 (사용자 메시지는 plain text)
- session_id를 응답 헤더 `X-Session-Id`에서 받아 `useRef`에 보관 → 같은 세션 내 대화 맥락 유지

---

# 6. 인프라 / Docker Compose

| 컨테이너 | 이미지 | 포트 |
|---|---|---|
| `pnt-postgres` | timescale/timescaledb:latest-pg16 | 5432 |
| `pnt-redis` | redis:7-alpine | 6379 |
| `pnt-backend` | 커스텀 (FastAPI, uvicorn --reload) | 8000 |
| `pnt-frontend` | 커스텀 (Vite dev server) | 5173 |

DB 스키마 핵심 테이블:
- `process_data` — TimescaleDB hypertable (time, line_id, station, param, value, unit), retention policy 적용
- `anomaly_events` — Layer1~3 결과
- `failure_alerts` — Layer4 결과
- `equipment`, `maintenance_reports` — 설비/예지보전

---

# 7. 도메인 지식 — 롤투롤 2차전지 전극 제조공정

피엔티(PNT)는 2차전지 전극을 만드는 **롤투롤(Roll-to-Roll) 공정 장비**를 만드는 회사입니다. 얇은 금속박(집전체) 위에 활물질 슬러리를 코팅하고, 압연하고, 자르고, 감는 일련의 연속 공정입니다.

```
[코팅 Coating] → [캘린더링 Calendering] → [슬리팅 Slitting] → [권취 Winding]
   슬러리 도포        압연(밀도↑/두께↓)        폭 절단              롤 권취
```

## 7.1 스테이션별 파라미터 (정상범위)

### ① Coating (코팅) — 슬러리를 금속박에 도포 후 건조
| 파라미터 | 단위 | 정상범위 | 의미 |
|---|---|---|---|
| line_speed | m/min | 15~25 | 라인 속도 |
| coating_thickness | μm | 80~120 | 코팅 두께 |
| coating_weight | mg/cm² | 15~20 | 단위면적당 도포량(목부착량) |
| dry_temp_zone1 | °C | 80~100 | 건조로 1구간 온도 |
| dry_temp_zone2 | °C | 100~130 | 건조로 2구간 온도 |
| dry_temp_zone3 | °C | 120~150 | 건조로 3구간 온도 |
| tension_supply | N | 30~50 | 공급부 장력 |
| tension_winding | N | 40~60 | 권취부 장력 |
| slurry_viscosity | cP | 3000~5000 | 슬러리 점도 |

### ② Calendering (캘린더링) — 압연으로 밀도/두께 조정
| 파라미터 | 단위 | 정상범위 | 의미 |
|---|---|---|---|
| roll_pressure | kN/m | 200~400 | 압연 롤 압력 |
| roll_temperature | °C | 60~80 | 롤 온도 |
| electrode_density | g/cm³ | 1.5~1.8 | 전극 밀도 |
| thickness_before | μm | 140~180 | 압연 전 두께 |
| thickness_after | μm | 80~120 | 압연 후 두께 |
| line_speed | m/min | 10~20 | 라인 속도 |

### ③ Slitting (슬리팅) — 정해진 폭으로 절단
| 파라미터 | 단위 | 정상범위 | 의미 |
|---|---|---|---|
| line_speed | m/min | 30~50 | 라인 속도 |
| tension | N | 20~40 | 장력 |
| slit_width_dev | mm | -0.1~0.1 | 절단 폭 편차 |
| blade_pressure | N | 10~30 | 칼날 압력 |

### ④ Winding (권취) — 최종 롤 형태로 감기
| 파라미터 | 단위 | 정상범위 | 의미 |
|---|---|---|---|
| tension | N | 20~35 | 장력 |
| winding_speed | m/min | 20~40 | 권취 속도 |
| roll_diameter | mm | 50~500 | 롤 직경 (계속 증가) |
| alignment_offset | mm | -0.5~0.5 | 정렬 오차 |

## 7.2 인과관계(물리 법칙) — 시뮬레이터 COUPLINGS

| 원인 | → | 결과 | 관계 |
|---|---|---|---|
| 슬러리 점도↑ | → | 코팅 두께↑ | 강한 양(+0.8) — 점도가 높으면 같은 갭에서도 더 두껍게 도포됨 |
| 라인 속도↑ | → | 코팅 중량↓ | 음(-0.5) — 빠르게 지나가면 단위면적당 도포량 감소 |
| 건조온도(Z2)↑ | → | 코팅 두께↓ | 음(-0.6) — 용매 증발↑ → 건조 후 두께 감소 |
| 코팅 두께↑ | → | (60틱 지연) 전극 밀도↑ | 양(+0.4) — 다음 공정(캘린더링)에 지연되어 영향 |
| 롤 압력↑ | → | 전극 밀도↑ | 강한 양(+0.7) — 캘린더링 핵심 물리 |
| 롤 압력↑ | → | 압연후 두께↓ | 음(-0.5) |

## 7.3 이상 패턴 5종 — 원인/관련변수/조치 (시스템 프롬프트 기반)

| 이상유형 | 한국어 | 원인 | 관련 파라미터 | 권장 조치 |
|---|---|---|---|---|
| TENSION_SPIKE | 장력 급변 | 장력 제어 이상, 롤 슬립 | tension_supply, tension_winding | 장력 제어기 점검, 주름/파단 여부 확인 |
| THICKNESS_DRIFT | 코팅 두께 점진 이탈 | 다이 갭 마모 | coating_thickness, slurry_viscosity | 다이 갭 측정/재조정 |
| TEMP_DEVIATION | 건조 온도 급변 | 히터 제어 이상 | dry_temp_zone1~3 | 히터/열전대 점검 |
| VISCOSITY_RISE | 슬러리 점도 상승 | 슬러리 경시 변화(열화) | slurry_viscosity, coating_thickness | 교반 강화, 잔여 사용기한 검토 |
| PRESSURE_OSC | 롤 압력 주기 진동 | 베어링 마모 | roll_pressure, electrode_density | 베어링 진동 측정/윤활/교체 |

## 7.4 Layer 1~4 탐지 체계 요약 (다시 정리)

```
Layer 1 (Z-score)        : "이 값이 최근 평균에서 너무 벗어났나?"  → 빠른 이상 감지
Layer 2 (EWMA 제어차트)   : "장기적으로 서서히 드리프트하고 있나?" → 느린 변화 감지
Layer 3 (Isolation Forest): "여러 변수를 동시에 보면 비정상 패턴인가?" → 다변량 이상
Layer 4 (Signature Engine): "변수들 사이의 '관계'가 평소와 달라졌나?" → 고장 전조 (가장 고급)
```

Layer 1~3은 **단일/다변량 값 자체**의 이상을, Layer 4는 **변수 간 상관관계의 구조 변화**를 봅니다. 예를 들어 베어링이 마모되면 압력값 자체는 정상범위 안에 있을 수 있지만 "압력↔밀도"의 평소 상관관계(0.7)가 깨지고(0.2), 압력에 주기적 진동(autocorrelation)이 나타납니다 — 이것이 `BEARING_WEAR` 시그니처입니다.

---

# 8. 면접/자소서용 한 줄 요약 포인트

- "단순 임계값 알람이 아니라, **변수 간 상관관계의 베이스라인을 학습**하고 그 구조가 깨지는 것을 탐지하는 4계층(Z-score → EWMA → Isolation Forest → 상관 시그니처) 이상탐지 파이프라인을 설계했습니다."
- "공정 시뮬레이터에 **물리적 인과결합(Coupling)**을 인코딩하여, 실제 설비 고장 시 나타나는 '관계 붕괴/반전/출현' 패턴을 재현하고 이를 탐지 로직으로 검증할 수 있게 했습니다."
- "벡터DB 없이 **통계적 특징 벡터 + 유클리드 거리 기반 유사사례 검색**으로 RAG 유사 구조의 예지보전 리포트를 LLM(gpt-5.4-mini/nano)으로 생성했습니다."
- "Pydantic AI 기반 에이전트가 **7개의 MES 도구(시계열 조회, 이상이력, 상관분석, 설비상태, 예지보전, 교대보고서, 테스트 주입)**를 함수 호출로 활용해 자연어 질의에 답합니다."
- "메시지 복잡도(길이/키워드)에 따라 **gpt-5.4-nano/mini를 자동 라우팅**하여 비용을 최적화했습니다."
