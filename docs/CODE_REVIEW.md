# PNT MES 코드 리뷰 — 문제점 및 개선사항

> 리뷰 범위: backend 전체(agents/services/routers/core/models), frontend 핵심(useMesAgent, useWebSocket, AgentChat, api), docker-compose, seed.py
> 작성일: 2026-06-10

---

## 1. 치명적 / 기능이 실제로 동작하지 않는 문제

### 1-1. 모델 라우팅(`routing.py`)이 완전히 죽은 코드 ⚠️ 최우선
`app/agents/routing.py`의 `select_model_id()` / `build_model()`은 **어디에서도 import되지 않습니다.**
`mes_agent.py:12`에서 모델이 `"openai:gpt-5.4-nano"`로 하드코딩되어 있어:

- `settings.openai_model_complex`(gpt-5.4-mini)는 영원히 사용되지 않음
- 프론트 UI에 표시되는 `"gpt-5.4-mini/nano"`(AgentChat.tsx:36)는 거짓 표기
- "복잡한 질문은 mini, 단순 질문은 nano" 라는 포트폴리오 핵심 어필 포인트가 실제로는 미구현

**수정 방향:** `agent.py`의 `_stream_agent()`에서 요청마다 모델을 주입:
```python
from app.agents.routing import build_model

async with mes_agent.run_stream(
    message,
    model=build_model(message),   # Pydantic AI는 run 단위 model 오버라이드 지원
    deps=deps,
    message_history=history,
) as result:
```

### 1-2. `feature_snapshot`이 실시간 탐지에서 절대 채워지지 않음 → RAG 검색 품질 붕괴
`predictive.py`의 "RAG-like" 유사 사례 검색은 `anomaly_events.feature_snapshot`에 의존하는데, **`anomaly_engine.py`의 `_persist_and_publish()`는 이 컬럼을 채우지 않습니다.** 현재 snapshot이 있는 데이터는 seed.py가 넣은 가짜 500건뿐입니다.

- 실제 탐지된 이벤트는 전부 `distance=50.0` 고정값 처리 (`predictive.py:139`)
- seed 데이터가 90일 lookback 윈도우를 벗어나는 순간 유사도 검색이 사실상 무의미해짐

**수정 방향:** `_ParamState`에 이미 rolling buffer(`self.buf`)가 있으므로, 이벤트 생성 시점에 `_extract_features()`와 같은 통계(mean/std/trend_slope/skewness)를 계산해서 `feature_snapshot`에 JSON으로 저장하면 됩니다. 이게 들어가야 "과거 유사 패턴 검색 → LLM 종합" 스토리가 진짜로 완성됩니다.

### 1-3. GPT-5.x 계열에서 `temperature` / `max_tokens` 파라미터 거부 가능성
`predictive.py:197-202`가 `temperature=0.3`, `max_tokens=400`을 사용합니다. OpenAI reasoning 계열 모델(gpt-5.x 포함)은 `max_tokens` 대신 `max_completion_tokens`를 요구하고 `temperature`는 기본값 외에 거부하는 경우가 많습니다. 이 경우 **API가 400을 반환 → 항상 except로 빠져서 rule-based fallback만 출력**되는데, fallback이 그럴듯해서 버그가 조용히 숨겨집니다.

**수정 방향:** 실제 호출 로그를 한 번 확인하고, 필요하면 `max_completion_tokens` 사용 + `temperature` 제거. fallback으로 빠질 때 `logger.exception`이 이미 있으니 로그 레벨/모니터링으로 표면화.

### 1-4. `get_db_optional()` — 이중 yield로 인한 RuntimeError 가능성
`database.py:43-53`: 라우트 핸들러에서 예외가 발생하면 그 예외가 generator의 첫 `yield` 지점으로 던져지고, 내부 `raise` → 바깥 `except Exception: yield None`이 **두 번째 yield**를 실행합니다. FastAPI dependency generator는 yield를 두 번 하면 RuntimeError를 내며 원래 예외를 가립니다.

**수정 방향:** 바깥 except는 "세션 *생성* 실패"만 잡도록 분리:
```python
async def get_db_optional():
    try:
        session_ctx = AsyncSessionLocal()
    except Exception:
        yield None
        return
    async with session_ctx as session:
        yield session
        await session.commit()
```

---

## 2. 에이전트 레이어 개선 (에이전틱 MES 방향에서 중요)

### 2-1. 이상탐지 이벤트 폭주 — 중복 억제(cooldown) 없음
`anomaly_engine.py`는 0.5초마다 모든 파라미터를 검사하고, 지속 이상(예: THICKNESS_DRIFT 200틱)에 대해 **틱마다 새 이벤트를 DB에 저장**합니다. 하나의 드리프트가 수십~수백 건의 중복 이벤트를 만들고:

- `anomaly_events` 테이블이 빠르게 오염됨
- 에이전트의 `get_anomaly_history` 결과가 같은 이상으로 도배됨
- 향후 "이벤트 → 에이전트 자동 분석" 트리거를 달면 LLM 호출 폭주로 직결

**수정 방향:** `(line, station, param, pattern_type)` 단위로 cooldown(예: 60초) 또는 "진행 중 이상은 기존 이벤트 업데이트" 방식 도입. 에이전틱 MES에서는 이게 비용 안전장치이기도 합니다.

### 2-2. 세션 rate limit이 클라이언트 신뢰 기반이라 우회 가능
`agent.py:123`: `session_id`를 클라이언트가 보내는 값으로 rate limit 키를 만듭니다. 매 요청마다 새 `session_id`(또는 빈 값 → 서버가 새 UUID 발급)를 보내면 **rate limit이 전혀 걸리지 않습니다.** 포트폴리오 데모를 외부에 공개하면 OpenAI 비용 직결 문제입니다.

**수정 방향:** `request.client.host`(IP) 기준 rate limit을 추가하거나 병행. 가능하면 일일 글로벌 토큰 예산(Redis 카운터)도.

### 2-3. 타임아웃 시 대화 기록이 통째로 유실
`agent.py:100-102`: 30초 타임아웃이 발생하면 `return`으로 빠져나가 `redis_append_conversation`이 호출되지 않습니다. 사용자에게는 부분 응답이 보였는데 다음 턴에서 에이전트는 그 대화 자체를 모릅니다.

**수정 방향:** 타임아웃 시에도 user 메시지 + 부분 응답(`full_response + "[중단됨]"`)을 저장.

### 2-4. 대화 히스토리 슬라이싱이 턴 경계를 깨뜨릴 수 있음
`agent.py:82`의 `[-_MAX_HISTORY_TURNS * 2:]`는 리스트가 홀수로 어긋나 있으면 assistant 메시지로 시작하는 히스토리를 만들 수 있습니다. 또한 tool call/result는 히스토리에 저장되지 않으므로(텍스트만 저장) 에이전트가 직전 턴에 조회한 수치를 "기억"하는 것은 순전히 응답 텍스트에 의존합니다 — 의도된 단순화라면 OK이지만 인지하고 있어야 합니다.

### 2-5. `retries=0`은 과도하게 엄격
Pydantic AI에서 `retries`는 무한루프 방지용이라기보다 **tool 인자 validation 실패 시 모델에게 재시도 기회를 주는 메커니즘**입니다. `retries=0`이면 모델이 인자를 한 번만 잘못 만들어도 (예: `line_id`에 문자열) 전체 런이 즉시 예외로 죽습니다. 루프 방지는 이미 30초 타임아웃이 담당하므로 `retries=1`이 비용/안정성 균형점입니다.

### 2-6. `inject_test_anomaly` 툴 — 에이전트에게 무방비 쓰기 권한
LLM이 채팅만으로 시뮬레이터 상태를 변경할 수 있습니다. 데모용으로는 좋지만, "에이전틱 MES"로 확장한다면 지금이 **액션 권한 모델을 설계할 시점**입니다:

- 읽기 툴(조회/분석) vs 쓰기 툴(주입/제어) 분리
- 쓰기 툴은 confirmation 단계(에이전트가 제안 → 사용자가 승인 → 실행) 또는 role 체크
- 모든 에이전트 액션을 audit log 테이블에 기록 (면접에서 어필 포인트가 됨)

### 2-7. 토큰 사용량/비용 추적 부재
`result.usage()`로 런별 토큰 수를 얻을 수 있는데 어디에도 기록하지 않습니다. 에이전틱 시스템에서 비용 관측성은 필수이고, Redis 카운터 + 일일 상한과 결합하면 2-2의 안전장치도 됩니다.

### 2-8. `get_anomaly_history` 요약 수치 버그
`tools.py:117-124`: `counts`가 `events[:10]` 루프 안에서만 집계되는데, 출력은 `"총 {len(events)}건: {summary}"`라서 이벤트가 10건을 넘으면 **총계와 심각도별 합계가 불일치**합니다. counts 집계를 전체 `events` 루프로 분리하세요.

---

## 3. 백엔드 일반

| # | 위치 | 문제 | 제안 |
|---|------|------|------|
| 3-1 | `simulator.py:283-293` | 5초마다 46행 insert를 행 단위 `session.add`로 수행 | `insert().values([...])` bulk insert 또는 asyncpg `copy` |
| 3-2 | `process_data` 테이블 | 보존 정책 없음 — 일 ~80만 행 누적, 무한 성장 | TimescaleDB `add_retention_policy('process_data', INTERVAL '7 days')` |
| 3-3 | `simulator.py:295` | DB persist 실패가 `logger.debug`로 묻힘 — 데이터 유실이 보이지 않음 | `warning` 레벨 + 실패 카운터 |
| 3-4 | `anomaly_engine.py:80-82` | EWMA 관리한계가 공정 평균이 아닌 **범위 중앙값 고정** 기준이고, `ewma_var`도 갱신 안 됨 — 시뮬레이터의 정상 drift도 이상으로 판정 | rolling mean 기준 중심선, 분산 온라인 갱신 |
| 3-5 | `main.py:64` | `allow_origins=["*"]` + `allow_credentials=True` 조합은 브라우저 스펙상 무효 (credential 요청 시 차단) | dev에서는 `["http://localhost:5173"]` 명시 |
| 3-6 | `main.py:48` | `except (asyncio.CancelledError, Exception)` — `Exception`이 이미 포괄, 의미 중복 | `except BaseException` 또는 `contextlib.suppress` |
| 3-7 | `agent.py` 응답 헤더 | `X-Session-Id`를 프론트가 읽으려면 CORS `expose_headers` 필요 — 현재 Vite proxy(동일 출처)라 우연히 동작 | `expose_headers=["X-Session-Id"]` 추가 |
| 3-8 | `mes_agent.py:12` | `"openai:gpt-5.4-nano"` 문자열 모델은 **환경변수 `OPENAI_API_KEY`에 직접 의존** — Docker(env_file)에선 동작하지만 로컬 단독 실행 시 secret 파일 기반 `settings.openai_api_key`가 무시됨 | 1-1의 `build_model()` 주입으로 일원화 |
| 3-9 | 테스트 없음 | anomaly engine·correlation·predictive처럼 순수 로직이 많은데 테스트 0개 — 포트폴리오 감점 요인 | `_ParamState.update`, `_risk_score`, `select_model_id`만이라도 pytest 추가 |
| 3-10 | `seed.py` | 멱등성 없음 — 두 번 실행하면 설비 10대가 20대로 | 이름 기준 upsert 또는 존재 체크 |

---

## 4. 프론트엔드

- **4-1. `useMesAgent.ts:80-88`** — 사용자가 Stop을 눌러도(AbortError) 이미 받은 부분 응답이 `"오류가 발생했습니다."`로 **덮어써집니다.** AbortError는 구분해서 부분 응답을 보존하세요. 또 진짜 오류일 때도 기존 내용에 append하는 편이 자연스럽습니다.
- **4-2. API 경로 이원화** — REST는 `VITE_API_URL`(axios, 직접 cross-origin) , 에이전트 채팅은 상대경로 `/api`(Vite proxy 경유)로 서로 다른 경로를 탑니다. 동작은 하지만 배포 구성이 바뀌면 한쪽만 깨집니다. `api.ts`의 BASE를 공유하도록 통일 권장.
- **4-3. `useMesAgent.ts:74`** — `if (payload.done) break;`는 안쪽 for문만 탈출하고 reader 루프는 계속 돕니다. 실해는 없지만 의도와 다르므로 플래그로 외부 루프도 종료 권장.
- **4-4. 429/타임아웃 UX** — rate limit(429) 응답이 일반 "오류가 발생했습니다"로 뭉개집니다. status별 메시지 분기 권장.

---

## 5. 보안 / 운영

- **5-1. `.env`에 실제 OpenAI API 키가 들어 있습니다.** 현재 git 저장소가 아니지만, 포트폴리오로 GitHub에 올리기 전에 반드시 `.gitignore`(`.env`, `*.env`) 먼저 만들고 `git init` 하세요. 한 번이라도 커밋되면 키 폐기가 답입니다.
- **5-2.** `docker-compose.yml`에 Postgres 평문 비밀번호 + 5432/6379 포트가 호스트에 노출 — 로컬 데모용으로는 허용 범위지만, README에 "데모 한정 구성"임을 명시하면 보안 인식을 어필할 수 있습니다.
- **5-3.** 시뮬레이터 제어(`/api/process/simulator/*`)와 이상 주입 API에 인증이 없음 — 공개 데모 시 누구나 라인을 멈출 수 있습니다.

---

## 6. 에이전틱 MES 확장 로드맵 제안

지금 구조(툴 콜링 챗봇)는 "에이전트가 *물어보면* 답하는" 수준입니다. 에이전틱으로 가려면:

1. **이벤트 드리븐 자율 분석** — `anomaly:live` 채널을 구독하는 백그라운드 에이전트 워커가 CRITICAL 이벤트 발생 시 자동으로 원인 분석(상관관계 + 유사 사례 조회)을 수행하고 결과를 대시보드/WebSocket으로 push. 단, 2-1의 이벤트 dedup이 선행 조건 (없으면 LLM 호출 폭주).
2. **계획-실행 분리 + 휴먼 인 더 루프** — 에이전트가 조치안을 구조화된 출력(Pydantic 모델)으로 제안 → 운전원 승인 → 실행 → 결과 검증 루프. `inject_test_anomaly`를 이 패턴의 첫 사례로 리팩토링하면 좋은 데모가 됩니다.
3. **에이전트 액션 감사 로그** — `agent_actions` 테이블 (시각, 세션, 툴, 인자, 결과, 토큰 사용량). 제조업 도메인에서 traceability는 면접 어필 포인트.
4. **feature_snapshot 파이프라인 완성 (1-2)** — 이게 돼야 "과거 사례 기반 예지보전"이 자기 강화 루프(탐지→축적→검색→예측)로 작동합니다.
5. **평가(eval) 셋** — 대표 질문 10~20개와 기대 동작(어떤 툴을 호출해야 하는지)을 정의한 회귀 테스트. LLM 비결정성 속에서 품질을 지키는 방법을 안다는 신호가 됩니다.

---

## 우선순위 요약

| 순위 | 항목 | 이유 |
|---|---|---|
| 1 | 1-1 모델 라우팅 연결 | 핵심 기능이 미작동, 수정 5줄 |
| 2 | 1-2 feature_snapshot 저장 | 예지보전 스토리의 근간 |
| 3 | 2-1 이벤트 dedup | DB 오염 + 향후 LLM 비용 폭주 방지 |
| 4 | 2-2 rate limit 우회 + 5-1 API 키 | 공개 데모 시 비용/보안 사고 |
| 5 | 1-3 GPT-5.x 파라미터 검증 | 조용한 fallback으로 숨은 버그 가능성 |
| 6 | 2-8, 1-4, 4-1 | 명백한 소형 버그들 |
