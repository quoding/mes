# PNT MES LLM Agent — 개발 회고록

> 작성일: 2026-06-09  
> 프로젝트: 피엔티 AI 자율제조 / MES 개발 직무 지원 포트폴리오

---

## 1. 프로젝트 개요

롤투롤(Roll-to-Roll) 방식 2차전지 전극 제조공정을 가상으로 시뮬레이션하고,  
LLM 에이전트가 실시간 공정 데이터를 분석·이상 탐지·예지보전하는 MES 시스템.

**핵심 기술 스택**
- Backend: FastAPI + Pydantic AI + OpenAI gpt-5.4-nano
- DB: PostgreSQL 16 + TimescaleDB (hypertable)
- 실시간: Redis Pub/Sub → WebSocket → Recharts
- Frontend: React 19 + TypeScript + Zustand v5 + Vite
- 인프라: Docker Compose (4 컨테이너)

---

## 2. 구현하면서 만난 버그들

### 2-1. `npm ci` 실패
**상황**: Docker 빌드 중 `pnt-frontend` 빌드 실패.  
**원인**: `package-lock.json`이 없는 상태에서 `npm ci` 실행.  
`npm ci`는 lockfile이 반드시 있어야 하는 명령어인데, 개발 초기에 lockfile 없이 커밋됨.  
**해결**: `npm install --package-lock-only` 로 lockfile 먼저 생성 후 재빌드.  
**교훈**: `package-lock.json`은 반드시 git에 포함해야 한다. `.gitignore`에서 제외 확인 필수.

---

### 2-2. React 무한 리렌더 루프 (`Maximum update depth exceeded`)
**상황**: 대시보드 접속 1초 후 모든 차트 컴포넌트가 사라지며 콘솔에 에러.  
**원인**: Zustand v5의 `useSyncExternalStore` 내부 구현 특성.

```typescript
// 문제 코드
const buf = useProcessStore((s) => s.buffers[key] ?? []);
//                                                    ^^^
// key가 없을 때마다 새로운 [] 인스턴스 반환
// React: 이전 스냅샷과 다름 → 리렌더 → 다시 다름 → 무한루프
```

**해결**: 모듈 레벨에 `EMPTY_BUF` 상수 선언 후 재사용.
```typescript
const EMPTY_BUF: { time: string; value: number }[] = []; // 모듈 레벨 상수
const buf = useProcessStore((s) => s.buffers[key] ?? EMPTY_BUF);
```

**교훈**: Zustand 셀렉터는 항상 **참조 안정성**을 보장해야 한다.  
셀렉터가 매 렌더마다 새 객체/배열을 반환하면 `Object.is` 비교를 통과하지 못해 무한루프가 발생.  
`useMemo`, 모듈 레벨 상수, `useShallow` 중 적합한 방법을 선택해야 한다.

---

### 2-3. WebSocket "closed before connection established"
**상황**: 대시보드에서 실시간 데이터가 표시되지 않음. 브라우저 콘솔에 WS 오류.  
**원인**: React 18 Strict Mode가 개발 환경에서 `useEffect`를 두 번 실행 (mount → unmount → remount).

```
1. mount: connect() 실행, WebSocket ws1 생성
2. unmount (cleanup): ws1.close() 호출
3. ws1.onclose 핸들러: setTimeout(connect, 3000) 예약
4. remount: connect() 또 실행, ws2 생성
5. 3초 후 타이머: connect() 또 실행, ws3 생성
   → 경쟁 상태: 연결되기 전에 닫히는 커넥션 발생
```

**해결**: `alive` 플래그로 cleanup 이후 retry 차단.
```typescript
let alive = true;
ws.onclose = () => {
  if (!alive) return;  // cleanup 후에는 retry 안 함
  setWsStatus("disconnected");
  retryTimer = setTimeout(connect, 3000);
};
return () => {
  alive = false;  // cleanup에서 플래그 해제
  clearTimeout(retryTimer);
  wsRef.current?.close();
};
```

**교훈**: React 18 Strict Mode는 사이드 이펙트의 클린업이 올바른지 검증하는 도구.  
WS, SSE, 타이머, 이벤트 리스너 등 외부 리소스를 다루는 모든 `useEffect`는  
cleanup 후 재진입을 막는 `alive`/`mounted` 플래그 패턴이 필수다.

---

### 2-4. Pydantic AI `async with override()` TypeError
**상황**: 에이전트 채팅 시 항상 `[에이전트 오류 발생]` 응답.  
백엔드 로그: `TypeError: '_GeneratorContextManager' object does not support the asynchronous context manager protocol`

**원인**: `Agent.override()`는 동기 컨텍스트 매니저인데 `async with`로 잘못 사용.
```python
# 잘못된 코드
async with mes_agent.override(model=model):  # ← TypeError
    async with mes_agent.run_stream(...) as result:
        ...

# 올바른 코드
async with mes_agent.run_stream(...) as result:
    # 모델을 Agent 초기화 시 고정하면 override 불필요
```

**교훈**: 라이브러리 API를 쓸 때 컨텍스트 매니저의 동기/비동기 여부를 반드시 확인해야 한다.  
Pydantic AI 1.0.x 기준 `override()`는 sync, `run_stream()`은 async.  
문서보다 실제 반환 타입(`__aenter__` 유무) 확인이 더 확실하다.

---

### 2-5. Pydantic AI `result_retries` Unknown keyword
**상황**: 백엔드 워커 프로세스 시작 실패.  
`pydantic_ai.exceptions.UserError: Unknown keyword arguments: 'result_retries'`

**원인**: Pydantic AI 0.x에서 1.0으로 올라오면서 `result_retries` 파라미터가 제거됨.  
requirements.txt에 `pydantic-ai-slim==1.0.18`을 명시했지만,  
코드는 이전 버전 API를 사용.

**해결**: `result_retries` 제거. 재시도 제어는 `retries=0`으로만 처리.

**교훈**: 빠르게 버전업 중인 라이브러리(Pydantic AI, LangChain 등)는  
설치 버전의 실제 생성자 시그니처를 컨테이너에서 직접 확인하는 게 가장 확실하다.
```bash
docker exec -it container python -c "import inspect, pydantic_ai; print(inspect.signature(pydantic_ai.Agent))"
```

---

### 2-6. EWMA 이상 탐지 과민 반응
**상황**: 시스템 가동 8시간 만에 WARNING 1,781건, CRITICAL 264건 발생.  
정상 범위 내 값도 WARNING으로 기록되는 현상.

**원인**: EWMA 제어차트의 초기 분산 추정치가 너무 좁았음.
```python
# 잘못된 설정
ewma_var = ((high - low) / 6) ** 2
# tension_supply (30~50N): UCL=43.3N, LCL=36.7N
# → 정상 범위(30~50N) 안에 있는 45N도 WARNING 탐지!

# 수정
ewma_var = ((high - low) / 4) ** 2  # 범위를 ±2σ로 모델링 → UCL/LCL 적절히 확대
```

**교훈**: 통계적 이상 탐지의 임계값 설정은 **도메인 지식과 실제 데이터 분포**를 모두 고려해야 한다.  
이론적으로 맞는 공식도 파라미터 특성에 따라 tuning이 필요하다.  
운영 전에 반드시 히스토그램으로 false positive rate를 검증해야 한다.

---

### 2-7. TimescaleDB `pg_stat_user_tables`에서 process_data = 0
**상황**: DB 상태 점검 중 `process_data` 테이블 row count가 0으로 표시.  
그런데 실제로는 데이터가 잘 들어가고 있음.

**원인**: TimescaleDB는 hypertable의 데이터를 내부적으로 chunk 테이블로 분산 저장.  
`pg_stat_user_tables`의 `process_data`는 부모 테이블이라 항상 0.  
실제 데이터는 `_hyper_1_1_chunk` 등의 청크 테이블에 있음.

```sql
-- 올바른 확인 방법
SELECT count(*) FROM process_data;  -- 뷰를 통해 전체 조회
-- 또는
SELECT * FROM timescaledb_information.hypertables;
```

**교훈**: TimescaleDB 사용 시 일반적인 PostgreSQL 모니터링 쿼리가 맞지 않을 수 있다.  
용량/row 확인은 TimescaleDB 전용 뷰(`timescaledb_information.*`)를 사용해야 한다.

---

## 3. 설계 시사점

### 3-1. 모델 라우팅의 실용성
처음에는 메시지 복잡도에 따라 nano/mini를 자동 라우팅하는 로직을 설계했다.  
하지만 포트폴리오 수준에서는:
- API 비용 예측이 어려워짐
- 모델별 응답 품질 차이 검증이 필요
- 라우팅 로직 자체가 버그 발생 지점

→ **nano 단일 모델로 단순화** 하고, 대신 안전장치(timeout, rate limit, max_tokens)를 강화하는 방향이 더 실용적이었다.

### 3-2. 무한루프/비용 폭탄 방지는 설계 시점에 고려해야 한다
LLM 에이전트는 Tool Use를 반복 호출하면서 무한루프에 빠질 수 있다.  
나중에 추가하려 하면 코드 구조를 많이 바꿔야 한다.  
**처음부터 들어가야 할 안전장치:**
- `retries=0` (툴 호출 재시도 없음)
- `asyncio.timeout()` (전체 응답 타임아웃)
- `max_tokens` 제한 (응답 길이 상한)
- 입력 메시지 길이 제한
- 히스토리 턴 수 제한 (컨텍스트 윈도우 낭비 방지)
- Redis rate limiting (세션당 분당 요청 제한)

### 3-3. Redis Pub/Sub vs WebSocket 브로드캐스트
```
Simulator → Redis PUBLISH → AnomalyEngine (subscribe)
                          → ws.py (subscribe) → 모든 WS 클라이언트
```
이 패턴의 장점:
- 시뮬레이터와 소비자가 완전히 분리됨
- 소비자(anomaly engine, websocket)를 독립적으로 스케일 가능
- 새 소비자 추가 시 시뮬레이터 코드 변경 불필요

단점:
- Redis가 SPOF(Single Point of Failure)
- 메시지 유실 가능 (Pub/Sub은 at-most-once)
- 운영 환경에서는 Redis Streams로 교체 검토 필요

### 3-4. uvicorn reload와 asyncio 백그라운드 태스크의 충돌
개발 환경에서 코드를 수정하면 uvicorn watchfiles가 변경을 감지해 reload를 시도한다.  
그런데 lifespan에서 실행 중인 `asyncio.create_task(simulator.run())`가  
graceful shutdown을 지연시켜 reload가 한참 걸리거나 멈추는 현상 발생.

근본 원인: uvicorn reload는 프로세스를 재시작하는 방식인데,  
백그라운드 태스크가 CancelledError를 올바르게 처리하지 않으면 지연.

**해결 방향**: 개발 중 잦은 수정이 필요한 경우 `docker restart`가 더 빠를 수 있다.  
또는 reload 지연을 막으려면 태스크에서 `asyncio.shield` 대신 명시적 CancelledError catch를 보장해야 한다.

### 3-5. RAG 없이 RAG처럼 — 통계적 패턴 매칭
벡터 DB와 임베딩 없이도 "RAG스러운" 예지보전을 구현할 수 있었다:
1. 현재 센서 상태 → 통계 피처 벡터 추출 (mean, std, trend, skewness)
2. 과거 이상 이력에서 동일 스테이션 후보 필터링
3. 정규화 유클리드 거리로 유사 사례 Top-3 선택
4. LLM에 컨텍스트로 주입 → 리포트 생성

이 접근법의 장점:
- 벡터 DB(Pinecone, Weaviate 등) 불필요 → 인프라 단순
- 물리적 의미가 있는 거리 (같은 단위계 피처끼리 비교)
- 설명 가능성 높음 (왜 유사한지 명확히 표현 가능)

단점:
- 피처 엔지니어링에 의존 (어떤 통계를 쓰느냐에 따라 결과가 크게 달라짐)
- 파라미터 스케일이 다르면 정규화 필수 (현재 미구현, 개선 여지)
- 진짜 의미적 유사성(semantic similarity)은 임베딩이 더 우수

---

## 4. 잘 된 점

- **Pydantic AI Tool Use**: 에이전트가 `query_process_data`, `get_anomaly_history` 등 7개 툴을 자율적으로 선택해 DB를 조회하는 것이 자연스럽게 작동
- **TimescaleDB 연동**: hypertable 덕분에 0.5초 간격 time-series INSERT가 일반 PostgreSQL 대비 훨씬 빠름. 실제로 10분도 안 돼 1만 행 돌파
- **3단계 이상 탐지**: Z-score (즉각 반응) + EWMA (드리프트 감지) + Isolation Forest (다변량) 레이어 구성이 서로 다른 패턴을 잡아내는 상호 보완 구조
- **SSE 스트리밍 + asyncio.timeout**: 30초 타임아웃이 걸리면 스트리밍 중에도 즉시 응답을 끊고 메시지를 내려줌 — 사용자 경험이 끊기지 않음

---

## 5. 개선 여지 (다음에 한다면)

| 항목 | 현재 | 개선 방향 |
|---|---|---|
| 이상 탐지 임계값 | 하드코딩 | 운영 데이터 기반 자동 튜닝 (MAD, percentile) |
| 예지보전 피처 정규화 | 미구현 | Min-Max 또는 Z-score 정규화 후 거리 계산 |
| 메시지 유실 | Redis Pub/Sub (at-most-once) | Redis Streams (at-least-once) |
| 에이전트 히스토리 | Redis list (TTL 24h) | 세션별 영구 저장 + 요약 압축 |
| 시뮬레이터 속도 | 고정 0.5초 | UI에서 배속 조정 가능하게 |
| 인증 | 없음 | JWT or API Key 기반 인증 |
| 모니터링 | 백엔드 로그만 | Prometheus + Grafana 연동 |

---

## 6. 2026-06-10 — 코드 리뷰 반영 + Layer 4 (상관분석 기반 고장 전조 알림) 구현

### 6-1. CODE_REVIEW.md 반영 (백엔드/프론트 전반)

- **에이전트 모델 라우팅 적용**: `run_stream(model=build_model(message))`로 메시지 복잡도에 따라 nano/mini 선택
- **레이트리밋 강화**: 세션 단위뿐 아니라 클라이언트 IP 단위로도 Redis INCR+EXPIRE 적용
- **타임아웃 시 대화 유실 방지**: 30초 타임아웃이 걸려도 지금까지의 응답을 `[응답 시간 초과 — 중단됨]`과 함께 Redis 대화이력에 저장
- **GPT-5.x 파라미터 호환성**: 예지보전 LLM 호출에서 `max_tokens`/`temperature` 제거 → `max_completion_tokens`로 교체 (gpt-5.4-nano가 구 파라미터를 거부하며 400 에러 발생하던 문제 해결)
- **`get_db_optional()` 이중 yield 버그 수정**, **이상 이벤트 dedup/cooldown(60초)** 추가, **이상 이력 집계(get_anomaly_history) 카운트 버그 수정**
- **TimescaleDB retention policy** 추가 (`process_data` 7일 보관)
- **CORS 설정 수정**: `allow_origins=["*"]` + `allow_credentials=True` 조합(브라우저 스펙 위반) → 명시적 origin 목록으로 교체
- **셧다운 시 `asyncio.CancelledError` 처리**: `except Exception` → `except BaseException`으로 수정 (Python 3.8+에서 CancelledError는 BaseException 상속)
- **`seed.py` 멱등성 확보**: 이미 시드된 경우 재실행 스킵
- **프론트엔드 SSE 훅 정비**: API_BASE 통일, 429(rate limit)/AbortError/일반 에러를 구분해 안내 메시지 추가, 스트림 종료 처리 버그 수정
- **`.gitignore` 추가**: `.env`, `__pycache__`, `node_modules` 등 비공개 처리

### 6-2. DESIGN_FAILURE_SIGNATURE.md — Layer 4 신규 구현

기존 3단계 이상 탐지(Z-score/EWMA/Isolation Forest)는 "이 값이 이상한가?"를 본다.  
Layer 4는 한 단계 더 나아가 **"파라미터 간의 관계(상관관계)가 이상한가?"**를 본다 — 설비 고장은 보통 단일 수치보다 먼저 파라미터 간 인과관계가 무너지는 형태로 전조 신호가 나타난다는 아이디어.

**시뮬레이터에 인과 결합(causal coupling) 추가**
- `Coupling(src, dst, gain, lag_ticks)` — 점도→두께, 라인속도→코팅중량, 압력→밀도 등 6개 파라미터 쌍에 인과관계 부여 (2-pass tick: 1차 독립값 계산 → 2차 결합 적용)
- `COUPLING_GAIN_OVERRIDES`: 기존 이상 시나리오(THICKNESS_DRIFT, VISCOSITY_RISE, PRESSURE_OSC, TEMP_DEVIATION)가 활성화되면 해당 결합의 gain이 변하도록 설정 → "고장 → 관계 변화 → 상관 변화"라는 인과 사슬을 시뮬레이션

**시그니처 엔진 (`signature_engine.py`)**
- 파라미터별 600틱(5분) 롤링 윈도우 유지
- Redis에 영속화되는 EWMA 베이스라인(상관계수 r, 표준편차) — 이상이 없을 때만 천천히 갱신되는 "self-immune" 방식
- 7종 atom 조건 평가: `CORR_BREAK`(상관 붕괴), `CORR_FLIP`(부호 반전), `CORR_EMERGE`(없던 상관 발생), `TREND_UP/DOWN`(추세), `VAR_SPIKE`(분산 급증), `OSC`(주기성/자기상관)
- `failure_rules.py`에 4개 고장 시그니처 정의: **BEARING_WEAR**(캘린더 롤 베어링 마모), **GAP_WEAR**(코팅 다이 갭 마모), **SLURRY_DEGRADE**(슬러리 경시 열화, 부분매칭), **HEATER_FAULT**(건조로 히터 제어 이상)
- `AlertGate` 상태머신(RAISED→ACTIVE→RESOLVED + 재발 쿨다운)으로 "하나의 고장 = 하나의 알림 레코드" 보장, 플래핑 방지

**API/실시간 알림**
- `models/alert.py` — `FailureAlert` ORM (failure_alerts 테이블)
- `routers/alerts.py` — `/alerts`, `/alerts/active`, `/alerts/{id}/ack`, `/alerts/engine-status`, `/alerts/baseline/reset`
- `routers/ws.py` — `/ws/alerts` (Redis `alert:live` pub/sub 브로드캐스트)
- `anomaly_engine.py`에 통합: process:live 틱마다 ingest, 30초마다 evaluate

**프론트엔드**
- `useAlerts` 훅 (REST 초기 로드 + WS 실시간 갱신), `alertStore`(zustand)
- `AlertBanner`(활성 알림 카드 + 확인 버튼), `AlertToastContainer`(RAISED/RESOLVED 토스트)
- `DashboardPage`에 통합

### 6-3. 검증 및 한계

- 백엔드 재시작 후 `failure_alerts` 테이블 자동 생성, retention policy 정상 적용 확인
- 가동 ~5분 후 양쪽 라인 모두 워밍업 완료(`warmed_up: true`, baseline 3 pairs / 5 params)
- `PRESSURE_OSC` 주입 후 5분간 예외/트레이스백 없이 ingest→evaluate→persist→publish 파이프라인 정상 동작
- 다만 가동 직후(짧은 윈도우에 정상/이상 구간이 섞인 상태)에는 OSC 신뢰도가 임계값(0.6)에 못 미쳐 알림이 발화되지 않음 — 베이스라인이 충분히 안정화된 장시간 가동 환경에서 정상 작동할 것으로 예상되는, 설계상 알려진 한계(휴리스틱 임계값)

---

*이 프로젝트는 피엔티 AI 자율제조 직무 지원을 위해 제작한 포트폴리오입니다.*
