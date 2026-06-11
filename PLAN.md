# 포트폴리오 개선 상세 계획 (PLAN)

> 전제: git repo는 별도로 직접 생성 (Phase 0 체크리스트만 확인).
> 목표: "잘 만든 데모" → "검증된 엔지니어링 증거"로 격상.
> 예상 소요: Phase 1 ≈ 3~4일, Phase 2 ≈ 1일, Phase 3 ≈ 반나절, Phase 4 ≈ 선택.

---

## Phase 0 — git 시작 전 체크리스트 (repo 만들 때 직접 확인)

- [ ] `.gitignore`에 다음이 포함되어 있는지 확인 후 첫 커밋:
  - `.env` (현재 루트에 실제 `.env` 존재 — **커밋되면 안 됨**)
  - `'피엔티'자소서.txt` (개인 문서 — repo 밖으로 옮기는 것을 권장)
  - `node_modules/`, `__pycache__/`, `.pytest_cache/`
- [ ] 첫 커밋은 "현재 상태 그대로" 하나로. 이후 Phase 1~3을 **작은 단위 커밋**으로 진행해 과정을 히스토리에 남김 (예: `test: Layer1 Z-score 스파이크 탐지 테스트 추가` → `fix: 이상 수명 off-by-one 수정`)

---

## Phase 1 — 핵심 탐지 로직 테스트 + 버그 수정 (최우선, 3~4일)

**왜:** 셀링 포인트인 4계층 탐지가 동작한다는 증거가 현재 0개. "주입 → 탐지"를 자동으로 증명하는 테스트가 이 포트폴리오 최고의 한 방.

### 1.1 테스트 인프라 (0.5일)

```
backend/
├── tests/
│   ├── conftest.py          # 공용 fixture
│   ├── test_anomaly_layers.py    # Layer 1~2 단위 테스트
│   ├── test_signature_atoms.py   # Layer 4 atom 판정 테스트
│   ├── test_alert_gate.py        # AlertGate 상태머신 테스트
│   ├── test_simulator.py         # 시뮬레이터 자체 검증
│   └── test_e2e_detection.py     # 주입→탐지 E2E (핵심)
└── pytest.ini (또는 pyproject.toml [tool.pytest.ini_options])
```

- `requirements.txt`에 추가: `pytest>=8`, `pytest-asyncio>=0.24` (dev 분리 원하면 `requirements-dev.txt`)
- `pytest.ini`: `asyncio_mode = auto`, `pythonpath = .`
- **DB/Redis 없이 돌게 만드는 게 핵심.** 현재 결합 지점과 대응:
  - `SignatureEngine._persist_and_publish` — DB/Redis 직접 호출 → 테스트에서는 monkeypatch로 이벤트만 리스트에 수집
  - `SignatureEngine._persist_baselines` / `restore_baselines` — `self._redis is None`이면 이미 no-op (그대로 활용)
  - `ProcessSimulator._tick` — Redis publish/hset 호출 → `_tick`을 분리 리팩토링: 값 계산부(`_compute_tick_readings() -> list[dict]`, 순수 함수에 가깝게)와 발행부(I/O)를 나눔. **테스트가 리팩토링을 강제하는 좋은 사례 — 커밋 메시지에 남길 것**
- `conftest.py` fixture:
  - `sim`: paused 해제된 `ProcessSimulator` (Redis 없이 값 계산만)
  - `sig_engine`: persist를 mock한 `SignatureEngine` (이벤트를 `captured: list`에 적재)
  - `make_series(n, mean, std, slope=0, osc_period=None)`: 합성 시계열 생성 헬퍼

### 1.2 단위 테스트 — Layer 1~2 (`test_anomaly_layers.py`, 0.5일)

`_ParamState`는 이미 순수 클래스라 바로 테스트 가능.

| 테스트 | 시나리오 | 기대 |
|---|---|---|
| `test_zscore_spike_critical` | 정상값 50틱 후 +5σ 스파이크 1개 | `result["zscore"]["severity"] == "CRITICAL"` |
| `test_zscore_normal_no_alarm` | 정상 가우시안 200틱 | zscore 키 없음 (오탐 0) |
| `test_ewma_catches_slow_drift` | 틱당 +0.1σ 느린 드리프트 100틱 | **Z-score는 침묵, EWMA는 WARNING** — 계층 존재 이유를 코드로 증명 |
| `test_threshold_severity_bands` | high×1.06 / high×1.16 값 | WARNING / CRITICAL 분기 확인 |
| `test_event_cooldown` | 같은 (line,station,param,pattern) 60초 내 2회 | 이벤트 1건만 기록 |

### 1.3 단위 테스트 — Layer 4 atoms (`test_signature_atoms.py`, 0.5일)

`SignatureEngine`에 합성 데이터를 직접 `ingest`하고 `_evaluate_line` 호출. 베이스라인은 `_corr_baseline`/`_std_baseline`에 직접 주입해 워밍업 생략.

| 테스트 | 베이스라인 | 현재 윈도우 | 기대 atom |
|---|---|---|---|
| `test_corr_break` | r=0.7 | 독립 노이즈 두 시계열 (r≈0) | `CORR_BREAK` |
| `test_corr_flip` | r=0.6 | 음의 상관 시계열 (r≈-0.6) | `CORR_FLIP` |
| `test_corr_emerge` | r=0.1 | 강한 양의 상관 (r≈0.8) | `CORR_EMERGE` |
| `test_var_spike` | std_base=1.0 | std=3.0 노이즈 | `VAR_SPIKE` |
| `test_trend_up_down` | — | slope ±(임계×1.5) 시계열 | `TREND_UP`/`TREND_DOWN` |
| `test_osc` | — | sin 주기 ≈ lag 20 시계열 | `OSC` (lag 검증 포함) |
| `test_no_atoms_on_normal` | 정상 베이스라인 | 베이스라인과 동일 분포 | atoms 비어 있음 |
| `test_warmup_skip` | — | `MIN_SAMPLES` 미만 | 평가 skip, 빈 리스트 |
| `test_min_conditions_partial` | SLURRY_DEGRADE 조건 1개만 충족 | — | 매칭됨 + confidence가 `matched/total` 비율로 하향 확인 |

### 1.4 단위 테스트 — AlertGate (`test_alert_gate.py`, 0.5일)

`_gate`를 persist mock 상태로 시나리오 구동:

1. `test_raise`: 첫 매칭 → `RAISED` 이벤트 1건
2. `test_update_no_duplicate`: 연속 매칭 → `UPDATED`만, 새 RAISED 없음 (중복 알림 방지 증명)
3. `test_resolve_after_misses`: 미매칭 4회(`RESOLVE_MISSES`) → `RESOLVED`
4. `test_rearm_within_cooldown`: RESOLVED 후 쿨다운 내 재매칭 → `RAISED`가 아닌 `ACTIVE` (플래핑 방지 증명)
5. `test_rearm_expired`: 쿨다운 10회 소진 후 재매칭 → 새 `RAISED`

### 1.5 시뮬레이터 검증 (`test_simulator.py`, 0.5일)

| 테스트 | 내용 |
|---|---|
| `test_normal_values_in_range` | 1000틱 구동, 모든 값이 정상범위 ±20% margin 내 |
| `test_coupling_produces_correlation` | 정상 운전 1000틱 → 점도↔두께 pearson r ≥ 0.4, 속도↔중량 r ≤ -0.3 (Coupling이 실제로 상관을 만든다는 증명) |
| `test_gain_override_breaks_correlation` | `THICKNESS_DRIFT` 활성 시 `_effective_gain`이 0.1 반환 |
| `test_lagged_coupling` | lag_ticks=60 결합이 60틱 지연 후 반영 |
| `test_anomaly_lifetime` | ticks=20 주입 → 정확히 20틱 후 비활성 (현재 off-by-one이라 **이 테스트는 처음엔 실패해야 정상** → 1.7에서 수정) |

### 1.6 E2E 주입→탐지 (`test_e2e_detection.py`, 1일 — 최고의 한 방)

구성: 시뮬레이터를 실시간 sleep 없이 틱 루프로 구동 → 매 틱 `sig_engine.ingest(readings)` → 60틱마다 `evaluate()` → 캡처된 이벤트 검사.

```python
async def run_scenario(sim, engine, warmup_ticks=1300, anomaly=None, run_ticks=600):
    """워밍업(베이스라인 형성) → 이상 주입 → 탐지까지 틱 수 반환"""
```

| 테스트 | 주입 | 기대 탐지 | 비고 |
|---|---|---|---|
| `test_bearing_wear_detected` | `PRESSURE_OSC` (line 1) | `BEARING_WEAR` RAISED | OSC + CORR_BREAK 동시 충족 |
| `test_heater_fault_detected` | `TEMP_DEVIATION` | `HEATER_FAULT` RAISED | VAR_SPIKE + CORR_FLIP |
| `test_gap_wear_detected` | `THICKNESS_DRIFT` | `GAP_WEAR` RAISED | CORR_BREAK + TREND_UP |
| `test_slurry_degrade_partial` | `VISCOSITY_RISE` | `SLURRY_DEGRADE` (낮은 confidence) | min_conditions=1 경로 |
| `test_no_false_positive_30min` | 없음 (정상 3600틱) | RAISED 0건 | **오탐율 0 증명** |
| `test_detection_latency` | 각 시나리오 | 주입 후 ≤ N틱 내 탐지 | N은 실측 후 결정, README에 표로 게재 |
| `test_alert_resolves_after_anomaly_ends` | 주입 → 종료 → 4 eval | RESOLVED 발행 | 수명주기 전체 검증 |

- 랜덤 시드 고정(`random.seed`, `np.random.seed`)으로 재현성 확보. 시드 민감하면 3개 시드로 파라미터라이즈.
- `settings.anomaly_inject_prob = 0` (자동 주입 끔) — fixture에서 설정.
- **부산물:** 탐지 지연 실측치 → README의 "탐지 성능" 표 데이터가 됨.

### 1.7 버그 수정 (테스트 선행 → 수정 → 통과 순서로 커밋, 0.5일)

1. **`simulator.py:287-289` off-by-one**: 필터 후 감소 → 감소 후 필터로 순서 교정. `test_anomaly_lifetime`이 검증.
2. **`signature_engine.py:328,334` 베이스라인 전체 정지**: `not atoms`(라인 전체) → 해당 pair/param과 관련된 atom이 없을 때만 갱신하도록 격리:
   ```python
   disturbed_params = {대상 param for atom in atoms}  # CORR_*는 pair 양쪽 param 포함
   # pair: 양쪽 param 모두 무관할 때만 갱신 / param: 본인이 무관할 때만 갱신
   ```
   회귀 테스트: `test_baseline_isolation` — 점도 TREND 발생 중에도 무관한 calendering 베이스라인은 계속 갱신됨.
3. **`simulator.py _persist_readings`**: row별 `session.add` 루프 → `session.add_all(rows)` 또는 Core `insert().values(rows)` 일괄 삽입. 예외 로그 `debug` → `warning` (삼킨 실패가 보이도록).

### Phase 1 완료 기준
- `cd backend && pytest` 전부 green, 테스트 ≥ 25개
- 탐지 지연 실측 수치 확보 (시그니처 4종 각각)
- 버그 3건 수정 커밋이 "실패 테스트 → 수정 → 통과" 순서로 히스토리에 남음

---

## Phase 2 — README + 문서 정합성 (1일)

### 2.1 `README.md` (채용 담당자가 처음 보는 파일)

구성 (위에서부터 30초 안에 핵심이 보이게):

1. **타이틀 + 한 줄 소개**: "2차전지 롤투롤 전극 공정의 설비 데이터를 실시간 수집·분석하고, 변수 간 상관관계 구조 변화로 고장 전조를 탐지하는 시스템"
2. **데모 GIF/스크린샷** (가장 중요, 3장):
   - 대시보드 전체 (실시간 차트 갱신 GIF)
   - 챗봇에 "베어링 마모 이상 주입해줘" → 알림 배너 발생 장면
   - AI 챗봇이 도구 호출로 데이터 분석하는 응답
   - 캡처: `docker compose up` 후 워밍업 5분 → `inject_test_anomaly` → 화면 녹화 (peek/Kooha 등) → `docs/images/`에 저장
3. **아키텍처 다이어그램**: PROJECT_GUIDE 1장 ASCII + 데이터 흐름도 발췌
4. **4계층 탐지 체계 표** + Layer 4 차별점 1문단 ("값이 아니라 관계를 본다")
5. **탐지 성능 표** (Phase 1.6 실측치):

   | 고장 시그니처 | 주입 시나리오 | 탐지 지연 | 30분 정상운전 오탐 |
   |---|---|---|---|
   | BEARING_WEAR | PRESSURE_OSC | N초 | 0건 |
6. **빠른 시작**: `.env.example` 복사 → `docker compose up -d` → http://localhost:5173 → 데모 시나리오 3줄
7. **테스트**: `cd backend && pytest` + 테스트가 검증하는 것 요약
8. **기술 스택 표** + **스코프 명시** (Phase 3 문구)
9. 상세 문서 링크: `docs/PROJECT_GUIDE.md` 등

### 2.2 문서 정리

- [ ] `docs/` 생성 → `PROJECT_GUIDE.md`, `DESIGN_FAILURE_SIGNATURE.md`, `DEVLOG.md`, `CODE_REVIEW.md` 이동, `docs/images/` 추가
- [ ] PROJECT_GUIDE에서 **Alembic 행 삭제** + `requirements.txt`의 `alembic==1.14.0` 제거 (실제 미사용 — 문서·의존성 둘 다 정리). 면접 대비 답: "데모 규모에선 startup 시 create_all + hypertable 초기화로 충분, 운영이라면 Alembic 도입"
- [ ] `'피엔티'자소서.txt` repo 밖으로 이동
- [ ] `.env.example`이 실제 필요한 변수와 일치하는지 대조

---

## Phase 3 — 포지셔닝 재조정 (0.5일)

**왜:** 작업지시/로트추적/라우팅 없는 시스템을 MES라 부르면 면접에서 역공당함. 장비 회사 지원엔 "설비 모니터링·고장 전조 탐지(EES/FDC 계열)"가 정확하고 유리.

- [ ] 명칭 일괄 변경: "PNT MES" → **"PNT Smart Factory Monitor — 설비 모니터링 & 고장 전조 탐지 시스템"** (또는 유사). 변경 지점:
  - `frontend/index.html` 타이틀, 헤더/사이드바 컴포넌트 문구
  - README, docs 문서들
  - docker-compose 컨테이너 이름은 유지해도 무방 (`pnt-*`)
- [ ] README에 스코프 선언 박스:
  > 이 프로젝트는 MES 전체가 아니라 **설비 데이터 수집(EES)과 이상탐지/고장전조(FDC) 영역**에 집중합니다. 작업지시·로트추적·라우팅 등 운영계 MES 기능은 의도적으로 스코프에서 제외했습니다.
- [ ] 면접 멘트 정리 (자소서 파일에 메모): "장비사 입장에서 고객사 MES와 맞물리는 데이터 인터페이스를 이해하려고 반대편(공장 운영) 관점에서 만들어봤다"

---

## Phase 4 — 선택 (Phase 1~3 완료 후에만)

우선순위 순:

1. **CI (GitHub Actions, 0.5일)**: `.github/workflows/test.yml` — push 시 `pytest` 실행 (DB/Redis 불필요하게 만든 Phase 1 덕에 services 없이 가능) + README에 배지. 가성비 최고.
2. **장비 인터페이스 시뮬레이션 (2~3일)**: 가상 코터 장비 프로세스가 별도 컨테이너로 떠서 OPC UA 스타일(또는 단순 JSON-over-WebSocket) 메시지로 레시피 다운로드/실적·알람 업로드 → "피엔티 장비 ↔ 고객사 시스템 인터페이스"를 직접 시연. 장비 회사 지원의 결정적 차별점이지만 공수 큼.
3. **탐지 성능 리포트 자동화**: 테스트 실행 시 시그니처별 탐지지연/오탐 표를 markdown으로 출력하는 스크립트 → README 갱신 자동화.

---

## 실행 순서 & 커밋 전략 요약

| # | 작업 | 산출물 | 커밋 단위 예시 |
|---|---|---|---|
| 0 | .gitignore 점검, 첫 커밋 | repo | `chore: initial import` |
| 1 | 테스트 인프라 + 시뮬레이터 I/O 분리 리팩토링 | `tests/`, conftest | `refactor: 시뮬레이터 값 계산과 발행 분리` |
| 2 | Layer 1~2, atoms, AlertGate 단위 테스트 | 테스트 ~20개 | `test: ...` 단위별 |
| 3 | 버그 3건 — 실패 테스트 → 수정 | fix 커밋 3개 | `fix: 베이스라인 갱신 파라미터 단위 격리` |
| 4 | E2E 주입→탐지 + 탐지지연 실측 | 성능 수치 | `test: 고장 시그니처 E2E 시나리오` |
| 5 | README(스크린샷 포함) + docs 정리 + alembic 제거 | README.md | `docs: ...` |
| 6 | 명칭/스코프 재포지셔닝 | UI·문서 반영 | `refactor: 프로젝트 포지셔닝 변경` |
| 7 | (선택) CI → 장비 인터페이스 | 배지, 신규 모듈 | — |
