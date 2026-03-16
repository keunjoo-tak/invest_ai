# Codex 작업 로그

## 인코딩 규칙
- 모든 소스와 문서는 UTF-8로 저장합니다.
- BOM은 사용하지 않습니다.
- 줄바꿈은 LF를 기본으로 사용합니다.
- PowerShell에서 한글이 깨질 수 있으므로, 한글 수정이 필요한 경우 유니코드 이스케이프 또는 UTF-8 강제 저장 방식으로 반영합니다.
- 저장 후 `U+FFFD`, `연속 물음표 4개` 패턴, BOM 존재 여부를 검사합니다.

## 2026-03-14 업데이트
### 1. 섹터 모멘텀 확장
- 입력 종목이 속한 섹터의 대장주 대비 커플링 지수, 자금 유입 강도, breadth, 상대 강도를 계산하도록 수정했습니다.
- `peer_rows`와 `sector_peer_snapshot`을 추가해 섹터 내 비교 근거를 응답과 리포트에 노출합니다.

### 2. 웹 리포트 개선
- `Stock Decision` 리포트에 섹터 모멘텀 요약과 peer 비교 표를 추가했습니다.
- `Action Planner` 리포트에도 섹터 모멘텀 근거와 peer 비교 표를 노출하도록 수정했습니다.

### 3. 수시공시 LLM 점수화
- 공급계약, 유상증자, 전환사채, BW, 자사주, 배당 공시를 호재/악재 점수로 수치화하는 단계를 추가했습니다.
- quick 모드에서도 공시 점수화가 수행되도록 파이프라인을 보강했습니다.
- 새 feature: `disclosure_bullish_score`, `disclosure_bearish_score`, `disclosure_net_score`, `material_disclosure_severity`

### 4. 검증
- `py -m compileall app tests` 성공
- `node --check app/web/app.js` 성공
- `py -m pytest -q tests` 성공 (`23 passed`)

## 2026-03-15 업데이트
### 1. 장전 미국 지수 전이 계수 반영
- `fetch_us_overnight_transmission()`을 추가했습니다.
- 장전 호출 시 미국 주요 지수 전일 수익률과 한국 종목 시가 갭 간의 베타/상관계수를 추정합니다.
- 새 feature
  - `overnight_us_beta`
  - `overnight_us_correlation`
  - `overnight_us_index_return`
  - `overnight_us_signal`
  - `overnight_us_vol_spillover`

### 2. 장전 판정 및 이벤트 모드 고도화
- 장전 적용 조건을 `한국 장 개장 전 + 미국 전일 종가 확정`으로 강화했습니다.
- 섹터별 미국 기준지수를 세분화했습니다.
  - 기술/반도체/인터넷 계열: `NASDAQ Composite`
  - 금융/산업재 계열: `DJIA`
  - 전통 소비/경기민감 업종: `S&P 500`
- 과거 유사 이벤트 가격 반응을 매칭하는 `event_pattern` 단계를 분석 파이프라인에 연결했습니다.
- 주요 이벤트 당일 또는 직후에는 `EVENT_DAY_VOLATILITY_MODE` 리스크 플래그가 붙고, 종목 판단과 행동 계획이 보수적으로 조정됩니다.
- 새 feature
  - `event_volatility_score`
  - `event_pattern_bias`
  - `event_pattern_confidence`

### 3. 사용자 리포트 반영
- `Stock Decision` 리포트에 아래 근거 섹션을 추가했습니다.
  - 이벤트 변동성 모드
  - 수시공시 점수화
  - 장전 미국 증시 영향

### 4. Market Regime 리포트 재구성
- instruction 기준으로 Market Regime 리포트 구성을 전면 재정리했습니다.
- 상단 핵심 결론, 시장 체제 분해, 핵심 원인 Top 5, 섹터 판단, 투자자 행동 연결, 반증 조건, 신뢰도 설명 영역으로 구분했습니다.
- 섹션별 접기/펼치기(`details`)를 추가해 보기 범위를 제어할 수 있게 했습니다.
- 대표 종목 표기는 `종목명(ticker)` 형식으로 통일했습니다.
- `MarketPulseEngine` 응답에 대표 종목 `name`을 추가했습니다.

### 5. 문서 반영
- `README.md`에 종목 리포트 추가 근거와 새 분석 변수 설명을 반영했습니다.

### 6. 검증
- `py -m compileall app tests` 성공
- `node --check app/web/app.js` 성공
- `py -m pytest -q tests` 성공 (`28 passed`)
- 변경 파일 인코딩 검사 완료 (`U+FFFD` 없음, `연속 물음표 4개` 패턴 없음)

### 7. Stock Decision 리포트 재구성
- `instruction/instruction.txt`의 Stock Decision 고도화안을 기준으로 기존 리포트 항목을 재정렬하고, 새로 필요한 항목을 추가했습니다.
- 기존 요약형 구성에서 `종목 투자 가설 검증 리포트` 구조로 전환했습니다.
- 이번에 새로 추가한 핵심 항목
  - 판단 유효 기간
  - 기준 시점과 데이터 반영 시각
  - 재무/가치/이벤트 리스크를 분리한 점수 구조 설명
  - 최근 새롭게 추가된 핵심 근거와 약해진 근거
  - 상충 신호와 판단을 가장 많이 바꾼 변수
  - 기간별 해석 문장
  - 시장-섹터-종목 계층 해석
  - 가격/수급/기술 경고
  - 이벤트/뉴스/공시 해석 세분화
  - 재무/실적/가치 판단 세분화
  - 거시/정책 민감도 설명
  - 체크포인트와 반증 조건
  - 데이터 신뢰와 설명 가능성 요약
- `Stock Decision` 리포트를 아래 접기/펼치기 섹션 카드로 재구성했습니다.
  - 상단 핵심 결론
  - 판단 점수 구조 분해
  - 왜 이런 결론이 나왔는지
  - 기간별 해석
  - 시장-섹터-종목 계층 분석
  - 가격/수급/기술 해석
  - 이벤트·뉴스·공시 해석
  - 재무/실적/가치 판단
  - 거시/정책 영향
  - 체크포인트 및 반증 조건
  - 데이터 신뢰 및 설명 가능성
- `Stock Decision` 상단 결론과 핵심 종목 표기는 `종목명(ticker)` 형식 기준을 유지했습니다.

### 8. 검증
- `node --check app/web/app.js` 성공
- `py -m compileall app tests` 성공
- `py -m pytest -q tests` 성공 (`28 passed`)
- 인코딩 검사 완료
  - `app/web/app.js`: UTF-8, BOM 없음
  - `codex.md`: UTF-8, BOM 없음
  - `U+FFFD` 없음
  - `연속 물음표 4개` 패턴 없음

### 9. Stock Decision 장애 수정 및 실검증
- `UnboundLocalError: event_pattern` 오류를 확인했고, `AnalysisPipeline.run()`에서 `event_pattern`을 생성하기 전 참조하던 순서 오류를 수정했습니다.
- 실호출 검증 중 `enrich_news_records()`가 정의되지 않은 `llm_disclosure_scores`를 참조하던 문제를 추가로 확인하고 제거했습니다.
- `news_parsed.url`, `disclosure_parsed.source_disclosure_id`가 전역 unique 제약인데 종목 단위로만 중복 검사하던 문제를 수정해, 저장 전 전역 기준으로 중복을 건너뛰도록 맞췄습니다.
- `state_label`, 섹터 요약 문구의 깨진 한글 문자열을 복구했습니다.

### 10. Stock Decision 무작위 표본 실검증
- 추출 기준: `random.Random(20260315)`
- KOSPI 표본: `207940`(삼성바이오로직스), `373220`(LG에너지솔루션), `000660`(SK하이닉스)
- KOSDAQ 표본: `086520`(에코프로), `196170`(알테오젠), `035900`(JYP Ent.)
- 검증 결과: 6건 모두 `GET /api/v1/stock-decision/{ticker}` `HTTP 200` 응답 확인
- 응답 경로: 6건 모두 `live_collection`
- 주요 결과
  - 삼성바이오로직스: `관찰`, `중립 또는 박스권`, confidence `57.56`, quality `78.0`
  - LG에너지솔루션: `관찰`, `중립 또는 박스권`, confidence `59.09`, quality `70.0`
  - SK하이닉스: `관찰`, `중립 또는 박스권`, confidence `49.58`, quality `69.0`
  - 에코프로: `관찰`, `중립 또는 박스권`, confidence `47.07`, quality `49.0`
  - 알테오젠: `보유`, `중립 또는 박스권`, confidence `66.88`, quality `70.0`
  - JYP Ent.: `관찰`, `중립 또는 박스권`, confidence `52.77`, quality `78.0`

### 11. Stock Decision 뉴스/거시 관련성 필터 강화
- `fetch_news()` 단계에서 종목 뉴스 결과를 그대로 쓰지 않고, 종목 직접 언급 여부와 주가 영향 문맥을 함께 점수화하는 관련성 필터를 추가했습니다.
- 뉴스 필터 로직은 아래 기준을 함께 사용합니다.
  - 종목명/영문명/별칭의 제목 또는 본문 직접 언급
  - 실적, 공급계약, 가이던스, 목표주가, 수급, 생산/출하 등 가격 영향 문맥
  - 코스피/거시 일반 기사 위주의 노이즈 패널티
- `NewsAPI` 조회 쿼리는 종목명과 영문명을 따옴표로 감싸 exact phrase 중심으로 조정했습니다.
- 외부 뉴스가 존재하지만 종목 관련성이 낮으면, 더미 fallback 뉴스를 대신 넣지 않고 빈 뉴스 집합으로 처리하도록 바꿈습니다.
- `Stock Decision`의 거시/정책 근거는 전역 거시 리스트를 그대로 쓰지 않고, 종목 섹터별 민감도에 맞는 지표만 선별하도록 재구성했습니다.
  - 수출/환율 민감 섹터: 환율·수출·글로벌 수요
  - 금리 민감 섹터: 금리·인플레이션
  - 내수 섹터: 소비·내수 심리
  - 반도체: 반도체 업황·미국 성장주 환경
- 장전 미국 지수 전이 항목은 기존대로 우선 노출하고, 그 외 거시 항목은 관련성 점수 기준으로 상위만 남기도록 했습니다.

### 12. 검증
- `py -m compileall app tests` 성공
- `py -m pytest -q tests` 성공 (`30 passed`)
- 추가 단위 테스트
  - `test_instrument_news_filter_keeps_only_stock_relevant_items`
  - `test_macro_summary_prefers_sector_relevant_rows`
- 실호출 점검
  - `GET /api/v1/stock-decision/005930` 성공 (`HTTP 200`)
  - 이벤트 타임라인 상위 제목이 삼성전자 직접 언급 기사 중심으로 정리된 것 확인
  - `policy_macro_summary`에 반도체 업황/환율 관련 항목만 우선 노출되는 것 확인

### 15. 사용자 노출 신호 한글 일관화
- 목적: 상승/하락 요인, 시그널 유형, 방향, 리스크 플래그가 영문 코드나 영문 문장으로 노출되지 않도록 사용자 응답 계층에 한글 로컬라이저를 추가했다.
- 구현 내용:
  - `app/services/localization/signal_localizer.py` 추가
  - `AnalyzeTickerResponse.signal`은 한글 라벨을 반환하고, 내부 판정용 코드는 `signal_type_code`, `direction_code`, `risk_flag_codes`에 별도로 보존
  - `app/services/alerts/formatter.py`에서 텔레그램 메시지 본문도 한글 라벨을 사용하도록 수정
  - `app/services/intelligence/decision_products.py`, `app/web/app.js`는 내부 판정이 필요한 경우 코드 필드를 우선 사용하도록 조정
- 검증:
  - `py -m compileall app tests` 성공
  - `py -m pytest -q tests` 성공 (`32 passed`)
  - 추가 테스트: `tests/test_signal_localization.py`
- 인코딩 메모:
  - PowerShell 경유 한글 치환을 피하기 위해 이번 수정은 사용자 노출 한글 문자열을 `\uXXXX` 기반으로 저장했다.

### 16. HANDOVER_FUNCTIONS.md - Market Regime 리포트 근거 문서화
- 목적: Market Regime 리포트 각 항목이 어떤 데이터와 계산 로직에서 나왔는지 인수인계 문서에 명확히 남겼다.
- 작업 내용:
  - `docs/HANDOVER_FUNCTIONS.md`에 Market Regime 리포트 섹션을 상세화했다.
  - `MarketPulseEngine.overview()`와 `app/web/app.js` 기준으로 체제 점수, 섹터 판단, 행동 가이드, 반증 조건의 계산 흐름을 정리했다.
  - 사용자 리포트에 노출되는 항목별 데이터 출처, 계산 방식, 해석 의미를 분리해 기록했다.
- 결과: Market Regime 리포트는 문서만 읽어도 결과 산출 근거를 코드 수준까지 추적할 수 있다.



### 17. HANDOVER_FUNCTIONS.md - Stock Decision 리포트 근거 문서화
- 목적: Stock Decision 리포트의 점수, 결론, 상승/하락 요인, 이벤트/재무/거시 근거가 어떤 데이터와 계산식으로 만들어지는지 문서화했다.
- 반영 내용:
  - `docs/HANDOVER_FUNCTIONS.md`를 UTF-8 기준으로 다시 작성
  - `Market Regime`, `Stock Decision` 두 제품의 리포트 항목별 근거를 코드 경로와 계산식 기준으로 정리
  - 사용자 설명 가능성을 높이기 위해 화면 문장과 실제 계산 로직의 연결 관계를 표와 규칙 설명으로 기록

## 2026-03-16 14:18:13 Action Planner 리포트 고도화 및 표본 검증
- `instruction/instruction.txt`의 Action Planner 고도화안 기준으로 리포트 항목을 재구성했다.
- 기존 화면 톤과 카드 스타일은 유지하고, 내용 구조만 상단 행동 결론 / 전제 조건 / 가격 구간 설계 / 실행 로드맵 / 보유 여부별 계획 / 투자 기간별 계획 / 위험 성향별 커스터마이즈 / 시나리오별 실행 전략 / 행동 근거 설명 / 체크리스트 및 무효화 조건으로 확장했다.
- `app/web/index.html`의 Action Planner 입력 폼에 `objective`, `avg_buy_price`를 추가했다.
- `app/web/app.js`에 `deriveActionContext()`, `renderActionReport()` 재구성을 반영해 리포트용 파생 항목과 접기/펼치기 섹션 카드를 추가했다.
- `app/schemas/decision_products.py`의 `ActionPlannerResponse`에 `investment_horizon`, `risk_profile`, `objective`, `has_position`, `avg_buy_price`, `action_score`, `plan_validity_window`를 추가했다.
- 실제 서비스 코드 `app/services/intelligence/decision_products.py`의 `build_action_plan()`이 새 스키마를 채우지 못하던 문제를 수정했다.
- `tests/test_web_and_api_smoke.py`의 Action Planner 더미 응답도 새 스키마에 맞게 갱신했다.
- 검증 결과:
  - `node --check app/web/app.js` 성공
  - `py -m compileall app tests` 성공
  - `py -m pytest -q tests` 성공 (`32 passed`)
- 무작위 표본 검증은 고정 시드 `20260316`을 사용했다.
- 코스피 표본 결과:
  - `LG화학(051910)` -> 200 / `관찰 유지` / 행동점수 `44.23` / 유효기간 `1~3주`
  - `LG에너지솔루션(373220)` -> 200 / `관찰 유지` / 행동점수 `50.66` / 유효기간 `1~3주`
  - `현대차(005380)` -> 200 / `관찰 유지` / 행동점수 `49.75` / 유효기간 `1~3주`
- 코스닥 표본 결과:
  - `에코프로(086520)` -> 200 / `관찰 유지` / 행동점수 `42.7` / 유효기간 `1~3주`
  - `펄어비스(263750)` -> 200 / `분할매수` / 행동점수 `62.5` / 유효기간 `1~3주`
  - `JYP Ent.(035900)` -> 200 / `관찰 유지` / 행동점수 `47.08` / 유효기간 `1~3주`
- 현재 `instrument_master.market`는 대부분 `KR`로 적재되어 있어, 코스피/코스닥 표본 추출은 검증용 대표 종목 풀에서 시드 기반 랜덤 샘플링으로 수행했다.

## 2026-03-16 21:15:31 네이버 섹션 헤드라인 배치 수집 및 Market Regime 반영
- 네이버 뉴스 섹션 페이지 크롤링 기능을 추가했다.
- 수집 대상 섹션:
  - 정치
  - 경제-금융
  - 경제-증권
  - 경제-부동산
  - IT/과학
  - 세계
- 구현 파일:
  - `app/services/ingestion/batch_ingestor.py`
  - `app/api/routes/batch_ingestion.py`
  - `app/workers/scheduler.py`
  - `app/services/intelligence/market_pulse.py`
  - `app/services/intelligence/decision_products.py`
  - `app/schemas/intelligence.py`
  - `app/schemas/decision_products.py`
  - `app/web/app.js`
  - `app/services/ingestion/source_catalog.py`
- 배치 수집 로직:
  - 섹션 페이지에서 기사 링크를 직접 추출한다.
  - 댓글 링크는 제외한다.
  - 기사 본문은 Naver 기사 페이지 `dic_area` 기반으로 추출한다.
  - 원문 HTML은 다운로드 폴더와 `external_document`에 함께 반영한다.
  - 본문 요약은 기존 Gemini `summarize_documents()` 경로를 재사용해 `summary_json`에 적재한다.
- 신규 배치 엔드포인트:
  - `POST /api/v1/batch/naver/headlines`
- 스케줄러:
  - 오전 `07:07`에 네이버 헤드라인 배치를 돌린 뒤 `07:10` 시장 체제 스냅샷을 생성하도록 추가했다.
- Market Regime 연동:
  - 최근 5일 `NAVER_HEADLINE_NEWS` 문서를 섹션별로 집계한다.
  - 섹션별 기사 수, 평균 감성, 평균 영향 점수, 대표 헤드라인을 바탕으로 `headline_news_briefs`를 생성한다.
  - 정치/경제/IT/세계 헤드라인이 시장 심리와 위험선호에 주는 영향을 설명하는 항목을 리포트에 추가했다.
- 웹 반영:
  - `Market Regime` 리포트에 `최근 5일 섹션별 헤드라인 영향` 섹션 카드를 추가했다.
- 테스트:
  - `py -m compileall app tests` 성공
  - `py -m pytest -q tests` 성공 (`35 passed`)
  - 추가 테스트 파일:
    - `tests/test_batch_naver_headlines.py`
    - `tests/test_market_headline_briefs.py`
- 실데이터 검증:
  - `BatchIngestor().ingest_naver_section_headlines(db, max_items=2)` 실행
  - 결과: `fetched_count=12`, `stored_count=12`, `skipped_count=0`
  - 저장 경로: `downloads/batch_naver_headlines_20260316T121102Z_3fc4117c-5196-4b5e-88b6-8049f6fedb4f`
  - `MarketPulseEngine().overview(date.today())` 실행 결과 `headline_news_briefs=6` 확인

## 2026-03-16 22:10:48 네이버 헤드라인 상세 팝업 및 운영 배치 버튼 추가
- `Market Regime` 리포트의 헤드라인 카드에 `상세 보기` 버튼을 추가했다.
- 상세 보기는 기존 사이드 패널을 재사용하는 방식으로 구현했다.
- 팝업에 표시되는 정보:
  - 섹션명
  - 기사 수
  - 영향 방향
  - 영향 초점
  - 최신 시각
  - 통합 요약
  - 원문 기사 제목 / 요약 / 링크
- `app/services/intelligence/market_pulse.py`에서 `headline_news_briefs[].top_articles`를 함께 내려주도록 확장했다.
- `app/web/index.html`의 `Batch Execution`에 `네이버 헤드라인` 버튼을 추가했다.
- `app/web/app.js`에서 `/api/v1/batch/naver/headlines` 실행 버튼을 연결했다.
- 검증:
  - `node --check app/web/app.js` 성공
  - `py -m compileall app tests` 성공
  - `py -m pytest -q tests` 성공 (`35 passed`)
  - `MarketPulseEngine().overview(date.today())` 실호출 시 `headline_news_briefs=6`, `top_articles` 포함 확인

## 2026-03-16 22:47:18 커밋 및 푸시 준비
- 현재 작업 트리 기준으로 커밋 및 원격 푸시를 진행한다.
- 임시 파일 `tmp_utf8_test.txt`는 커밋 대상에서 제외하고 삭제했다.
- 나머지 변경 파일은 현재 상태 그대로 커밋한다.

## 2026-03-16 22:48:41 커밋 대상 정리
- `instruction/tmp.txt`는 임시 복사본으로 판단해 커밋 대상에서 제거했다.
- 나머지 스테이징 상태를 유지한 채 커밋을 진행한다.

## 2026-03-16 22:49:54 커밋 생성
- 커밋 해시: `dfc647b`
- 커밋 메시지: `feat: upgrade decision products and market intelligence`
- 다음 단계로 `origin/main` 푸시를 진행했다.
