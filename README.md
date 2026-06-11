# PNT Smart Factory Monitor

**2차전지 롤투롤 전극 공정 설비 모니터링 & 고장 전조 탐지 시스템**

설비 시계열 데이터를 실시간으로 수집·분석하고, 단순 임계값이 아니라 **변수 간 상관관계 구조의 변화**로 고장 전조를 탐지합니다. Pydantic AI 기반 챗봇 에이전트가 자연어로 공정 데이터를 분석합니다.

> **스코프**: 이 프로젝트는 MES 전체가 아니라 **설비 데이터 수집(EES)과 이상탐지/고장전조(FDC) 영역**에 집중합니다. 작업지시·로트추적·라우팅 등 운영계 MES 기능은 의도적으로 스코프에서 제외했습니다.

<!-- TODO: 스크린샷 캡처 후 교체
![대시보드](docs/images/dashboard.png)
![고장 전조 알림](docs/images/alert-demo.gif)
![AI 에이전트](docs/images/agent-chat.png)
-->

## 핵심: 4계층 이상탐지 파이프라인

| Layer | 기법 | 답하는 질문 |
|---|---|---|
| 1 | Z-score (롤링 50틱) | 이 값이 최근 평균에서 너무 벗어났나? |
| 2 | EWMA 제어차트 | 서서히 드리프트하고 있나? (Z-score가 못 잡는 느린 변화) |
| 3 | Isolation Forest | 여러 변수를 동시에 보면 비정상 패턴인가? |
| 4 | **상관 시그니처 엔진** | **변수들 사이의 '관계'가 평소와 달라졌나?** |

Layer 4가 이 프로젝트의 차별점입니다. 예를 들어 베어링이 마모되면 압력값 자체는 정상범위 안에 있어도, 평소의 "압력↔밀도" 상관(r≈0.55)이 붕괴하고 압력에 주기 진동이 나타납니다. 엔진은 정상 운전 중 상관/분산 베이스라인을 학습(자기면역 EWMA)하고, 그 구조가 깨지는 패턴(`CORR_BREAK/FLIP/EMERGE`, `TREND`, `VAR_SPIKE`, `OSC`)을 고장 시그니처 규칙과 매칭합니다.

공정 시뮬레이터에는 물리적 인과결합(Coupling)이 인코딩되어 있어, 고장 시나리오가 활성화되면 값만 튀는 게 아니라 **변수 간 관계 자체가 변조**됩니다 — 탐지 대상과 탐지 로직의 인과가 닫혀 있어 E2E로 검증 가능합니다.

## 탐지 성능 (E2E 테스트 실측)

| 고장 시그니처 | 주입 시나리오 | 탐지 지연 | confidence |
|---|---|---|---|
| 캘린더 롤 베어링 마모 (CRITICAL) | 압력 주기 진동 | 40초 | 0.92 |
| 건조로 히터 제어 이상 (CRITICAL) | 온도 급변+발진 | 10초 | 0.83 |
| 코팅 다이 갭 마모 (WARNING) | 두께 점진 드리프트 | 250초 | 0.78 |
| 슬러리 경시 열화 (WARNING) | 점도 상승 | 190초 | 0.25 (1차 경보) |
| 정상 운전 30분 | — | 오탐 0건 | — |

*0.5초/틱 시뮬레이션 기준, `backend/tests/test_e2e_detection.py`가 자동 검증.*

## 빠른 시작

```bash
cp .env.example .env          # OPENAI_API_KEY만 채우면 됨 (챗봇 기능용)
docker compose up -d
# http://localhost:5173 접속 → 시뮬레이터 시작 → 5분 워밍업 후
# 챗봇에 "베어링 마모 이상 주입해줘" 입력 → 실시간 알림 확인
```

## 테스트

```bash
cd backend
pip install -r requirements-dev.txt
pytest        # 30 tests — DB/Redis 불필요, 약 1분
```

단위 테스트 24개(Z-score/EWMA/atom 판정/AlertGate 상태머신/시뮬레이터) + E2E 6개(고장 주입→시그니처 탐지·탐지지연 측정·오탐 0건 검증). 시뮬레이터의 값 계산과 I/O를 분리해 모든 테스트가 외부 의존성 없이 실행됩니다.

## 아키텍처

```
ProcessSimulator (0.5초/틱, 물리 인과결합 인코딩)
   ├─► TimescaleDB (hypertable, 시계열 저장)
   └─► Redis Pub/Sub "process:live"
         ├─► AnomalyEngine  (Layer 1~3) ─► anomaly_events + "anomaly:live"
         ├─► SignatureEngine (Layer 4)  ─► failure_alerts + "alert:live"
         └─► WebSocket /ws/live ─► React 대시보드 (실시간 차트/알림)

사용자 질문 → Pydantic AI 에이전트 (도구 7종: 시계열 조회·이상이력·상관분석·
설비상태·예지보전·교대보고서·이상주입) → SSE 스트리밍 응답
```

## 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 16 + TimescaleDB · Redis 7 |
| 분석/ML | NumPy · SciPy · scikit-learn (Isolation Forest) |
| AI | Pydantic AI · OpenAI gpt-5.4-nano (비용 최적화를 위한 경량 단일 모델) |
| Frontend | React 19 · TypeScript · Vite · Zustand · TanStack Query · Recharts · TailwindCSS |
| Infra | Docker Compose (4 컨테이너) |

## 상세 문서

- [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) — 아키텍처·코드·도메인 지식 전체 해설
- [docs/DESIGN_FAILURE_SIGNATURE.md](docs/DESIGN_FAILURE_SIGNATURE.md) — Layer 4 설계 문서
- [docs/DEVLOG.md](docs/DEVLOG.md) — 개발 일지
