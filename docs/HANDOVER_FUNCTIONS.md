# 함수/클래스 인수인계 가이드

이 문서는 `app/`, `scripts/`, `tests/`의 주요 함수/클래스를 인수인계 관점으로 요약한 문서입니다.
구성: `기능` / `처리 방식` / `I/O 예시`

## 1) 앱 진입점

### `app/main.py`

#### `on_startup()`
- 기능: 애플리케이션 시작 시 DB 테이블 생성과 스케줄러 시작.
- 처리 방식: `Base.metadata.create_all(bind=engine)` -> `scheduler.start()`.
- I/O 예시:
  - 입력: 없음
  - 출력: 없음(부수효과: DB 테이블/스케줄러 준비)

#### `on_shutdown()`
- 기능: 애플리케이션 종료 시 스케줄러 정리.
- 처리 방식: `scheduler.shutdown(wait=False)`.
- I/O 예시:
  - 입력: 없음
  - 출력: 없음

## 2) API 라우터

### `app/api/routes/health.py`

#### `health() -> HealthResponse`
- 기능: 서버 상태 확인.
- 처리 방식: 설정값(`app_name`, `app_env`) + 현재 UTC 시각 반환.
- I/O 예시:
  - 입력: 없음
  - 출력: `{"status":"ok","app":"InvestAI Signal Alert Service","env":"dev","time_utc":"..."}`

### `app/api/routes/analysis.py`

#### `analyze_ticker(req, db) -> AnalyzeTickerResponse`
- 기능: 종목 분석 파이프라인 실행.
- 처리 방식: `AnalysisPipeline.run()` 호출.
- I/O 예시:
  - 입력: `{"ticker_or_name":"005930","lookback_days":365,"notify":true}`
  - 출력: 신호/피처/설명/알림결과 포함 응답

### `app/api/routes/internal.py`

#### `_now() -> datetime`
- 기능: UTC 현재 시각 헬퍼.
- 처리 방식: `datetime.now(timezone.utc)`.
- I/O 예시:
  - 입력: 없음
  - 출력: `2026-02-28T12:00:00+00:00`

#### `recompute_features() -> dict`
- 기능: 내부 작업 트리거 샘플.
- 처리 방식: 매크로 샘플 조회 후 건수 반환.
- I/O 예시:
  - 입력: 없음
  - 출력: `{"status":"queued","macro_rows":2}`

#### `resolve_instrument(req) -> IngestionProbeResponse`
- 기능: 입력 종목명/티커를 최종 티커로 정규화.
- 처리 방식: `providers.resolve_instrument()` 결과를 진단 포맷으로 반환.
- I/O 예시:
  - 입력: `{"ticker_or_name":"네이버"}`
  - 출력: `details.ticker="035420", details.name_kr="NAVER"`

#### `search_instrument_candidates(req) -> InstrumentSearchResponse`
- 기능: 텍스트 유사도 기반 후보 검색.
- 처리 방식: `providers.search_instruments(query, limit)` 호출.
- I/O 예시:
  - 입력: `{"query":"하이닉스","limit":5}`
  - 출력: `[{"ticker":"000660","name_kr":"SK하이닉스","score":0.99,...}, ...]`

#### `probe_kis_daily_price(req) -> IngestionProbeResponse`
- 기능: KIS 일봉 수집 단독 점검.
- 처리 방식: 종목 resolve 후 `_fetch_price_daily_kis()` 직접 호출.
- I/O 예시:
  - 입력: `{"ticker_or_name":"005930","lookback_days":30}`
  - 출력: `sample=[{"trade_date":"2026-02-27","close":...}, ...]`

#### `probe_naver_news(req) -> IngestionProbeResponse`
- 기능: NAVER 뉴스 수집 단독 점검.
- 처리 방식: `_fetch_news_naver()` 호출.
- I/O 예시:
  - 입력: `{"ticker_or_name":"삼성전자","max_items":5}`
  - 출력: `sample=[{"title":"...","url":"...","publish_time_utc":"..."}, ...]`

#### `probe_dart_corp_code(req) -> IngestionProbeResponse`
- 기능: 티커 -> DART `corp_code` 매핑 점검.
- 처리 방식: `_load_dart_corp_code_map()` 조회.
- I/O 예시:
  - 입력: `{"ticker_or_name":"005930"}`
  - 출력: `details={"ticker":"005930","corp_code":"00126380",...}`

#### `probe_dart_disclosures(req) -> IngestionProbeResponse`
- 기능: DART 공시 목록 수집 점검.
- 처리 방식: `_fetch_disclosures_dart()` 호출.
- I/O 예시:
  - 입력: `{"ticker_or_name":"005930","days":30}`
  - 출력: `sample=[{"source_disclosure_id":"...","title":"..."}, ...]`

#### `probe_macro_snapshot(req) -> IngestionProbeResponse`
- 기능: 매크로 스냅샷 점검.
- 처리 방식: `fetch_macro(as_of_date)` 반환값 래핑.
- I/O 예시:
  - 입력: `{"ticker_or_name":"005930"}`
  - 출력: `sample=[{"indicator_name":"KRWUSD_DAILY_CHANGE",...}, ...]`

#### `probe_x_recent_search(req) -> IngestionProbeResponse`
- 기능: X Recent Search 호출 점검.
- 처리 방식: Bearer 토큰 확인 -> `/2/tweets/search/recent` 호출 -> 상태/에러 진단 반환.
- I/O 예시:
  - 입력: `{"query":"삼성전자","max_results":10}`
  - 출력: `details.http_status=200|402|401`, `sample=[...]`

#### `collect_external_bundle(req) -> CollectExternalBundleResponse`
- 기능: 외부 수집 소스 전체 번들 점검(KIS/NAVER/DART/매크로).
- 처리 방식: 각 소스 호출 후 소스별 `IngestionProbeResponse` 배열 구성.
- I/O 예시:
  - 입력: `{"ticker_or_name":"005930","lookback_days":30,"max_items":5,"days":30}`
  - 출력: `sources=[{"source":"kis_daily_price",...},{"source":"naver_news",...}, ...]`

## 3) 파이프라인 계층

### `app/services/pipeline/orchestrator.py`

#### `class AnalysisPipeline`
- 기능: 분석 전체 오케스트레이션(수집 -> 저장 -> 피처 -> 신호 -> 설명 -> 알림).

#### `__init__()`
- 처리 방식: `SourceProviderClient`, `GeminiClient`, `TelegramNotifier` 준비.
- I/O 예시: 입력 없음 / 출력 없음

#### `_get_or_create_instrument(db, ticker_or_name) -> Instrument`
- 기능: 종목 정규화 후 `instrument_master` 조회/신규 생성.
- 처리 방식: resolve -> DB select -> 없으면 insert.
- I/O 예시:
  - 입력: `"네이버"`
  - 출력: `Instrument(ticker="035420", name_kr="NAVER", ...)`

#### `_persist_collected_data(db, instrument, prices, news, disclosures, macro_rows) -> None`
- 기능: 수집 데이터 저장(중복 방지 포함).
- 처리 방식:
  - 가격: `(instrument_id, trade_date)` 중복 skip
  - 뉴스: `url` 중복 skip
  - 공시: `source_disclosure_id` 중복 skip
- I/O 예시:
  - 입력: 수집 dict 리스트들
  - 출력: 없음(부수효과: DB insert)

#### `run(db, req) -> AnalyzeTickerResponse`
- 기능: 분석 API의 실질 실행 함수.
- 처리 방식:
  - 수집(`fetch_*`) -> 저장 -> 피처(`build_features`) -> 신호(`evaluate_signal`)
  - 품질 게이트 -> LLM 설명 -> 중복 억제 -> 텔레그램 발송 -> 결과 응답
- I/O 예시:
  - 입력: `AnalyzeTickerRequest`
  - 출력: `AnalyzeTickerResponse`

## 4) 수집 계층

### `app/services/ingestion/providers.py`

#### `class InstrumentProfile`
- 기능: 정규화된 종목 프로필 DTO.
- 필드: `ticker`, `name_kr`, `market`, `sector`

#### `class SourceProviderClient`
- 기능: 종목 식별/외부 API 수집/폴백 데이터 제공.

#### `resolve_instrument(ticker_or_name) -> InstrumentProfile`
- 기능: 입력값을 단일 종목으로 정규화.
- 처리 방식: 숫자티커 우선 -> alias -> 유사도 검색 -> fail-soft fallback.
- I/O 예시:
  - 입력: `"현대차"`
  - 출력: `InstrumentProfile(ticker="005380", name_kr="현대자동차", ...)`

#### `search_instruments(query, limit=10) -> list[dict]`
- 기능: 자연어 종목명/티커 후보 검색.
- 처리 방식: DART 카탈로그 + alias 결과 병합, 유사도 점수 정렬.
- I/O 예시:
  - 입력: `("하이닉스", 5)`
  - 출력: `[{"ticker":"000660","name_kr":"SK하이닉스","score":0.999,...}, ...]`

#### `fetch_price_daily(ticker, as_of_date, lookback_days) -> list[dict]`
- 기능: 일봉 데이터 수집(실패 시 fallback).
- 처리 방식: `_fetch_price_daily_kis()` 실패 시 `_fallback_price_daily()`.

#### `fetch_news(ticker, as_of_date) -> list[dict]`
- 기능: 뉴스 수집(실패 시 fallback).
- 처리 방식: `_fetch_news_naver()` 실패 시 `_fallback_news()`.

#### `fetch_disclosures(ticker, as_of_date) -> list[dict]`
- 기능: 공시 수집(실패 시 fallback).
- 처리 방식: `_fetch_disclosures_dart()` 실패 시 `_fallback_disclosures()`.

#### `fetch_macro(as_of_date) -> list[dict]`
- 기능: 매크로 스냅샷 제공.
- 처리 방식: 현재는 정적 샘플 2건 반환.

#### `_fetch_price_daily_kis(...)`
- 기능: KIS OpenAPI 일봉 조회.
- 처리 방식: 토큰 발급 -> 조회 -> 날짜 필터/정렬.

#### `_issue_kis_access_token(...)`
- 기능: KIS OAuth 토큰 발급.

#### `_kis_base_candidates()`
- 기능: KIS base URL 우선순위 리스트 생성(`custom -> prod -> mock`).

#### `_fetch_news_naver(...)`
- 기능: NAVER 검색 뉴스 조회.
- 처리 방식: HTML 제거, 시간 파싱, 단순 감성점수 부여.

#### `_fetch_disclosures_dart(...)`
- 기능: DART 공시 목록 조회.
- 처리 방식: 티커->corp_code 매핑 후 `list.json` 호출, 이벤트 분류/임팩트 산정.

#### `_load_dart_corp_code_map()`
- 기능: 티커->corp_code dict 반환.

#### `_load_dart_instrument_catalog()`
- 기능: DART `corpCode.xml` 카탈로그 로딩/12시간 캐시.
- 처리 방식: ZIP/XML 파싱 후 fallback 카탈로그 merge.

#### `_extract_corp_code_xml_bytes(content)`
- 기능: ZIP 응답에서 XML 바이트 추출.

#### `_fallback_price_daily(...)`
- 기능: 가격 fallback 시뮬레이션 데이터 생성.

#### `_fallback_news(...)`
- 기능: 뉴스 fallback 샘플 생성.

#### `_fallback_disclosures(...)`
- 기능: 공시 fallback 샘플 생성.

#### `_fallback_catalog()`
- 기능: 대표 종목 카탈로그 fallback 제공.

#### `_find_catalog_by_ticker(ticker)`
- 기능: 카탈로그에서 특정 티커 행 조회.

#### `_search_alias_candidates(query)`
- 기능: alias 기반 후보 생성/점수화.

#### `_alias_map()`
- 기능: 대표 별칭 맵 구성(예: 네이버/NAVER, 현대차/현대자동차).

#### `_norm_text(value)`
- 기능: 검색 텍스트 정규화(공백/기호/법인표기 제거).

#### `_similarity(a, b)`
- 기능: 문자열 유사도 계산(`SequenceMatcher`).

#### `_to_float(v)`
- 기능: 숫자 문자열/콤마 제거 변환.

#### `_strip_html(s)`
- 기능: HTML 태그 제거 + 엔티티 unescape.

#### `_parse_naver_pubdate(s)`
- 기능: NAVER `pubDate` 파싱.

#### `_parse_yyyymmdd(s)`
- 기능: `YYYYMMDD` 문자열 UTC datetime 변환.

#### `_naive_sentiment(title)`
- 기능: 키워드 기반 단순 감성 점수.

#### `_classify_disclosure(title)`
- 기능: 공시 제목을 `contract/earnings/financing/mna/general` 분류.

#### `_estimate_disclosure_impact(title)`
- 기능: 공시 유형별 임팩트 점수 반환.

## 5) 신호/품질/피처/알림/LLM

### `app/services/features/feature_builder.py`

#### `_rsi14(closes) -> float`
- 기능: RSI(14) 계산.
- I/O 예시:
  - 입력: `[100, 101, ...]`
  - 출력: `57.3`

#### `build_features(as_of_date, prices, news, disclosures, macro) -> MarketFeatureSet`
- 기능: 파이프라인용 피처 생성.
- 처리 방식: 이동평균/RSI/변동성/상대거래량/뉴스/공시/매크로 집계.

### `app/services/signal/scorer.py`

#### `evaluate_signal(features) -> SignalResult`
- 기능: 룰 기반 점수화 및 신호 타입 결정.
- 처리 방식: MA/RSI/거래량/뉴스/공시/매크로 반영 후 `score`, `quality_score` 산출.

### `app/services/quality/gates.py`

#### `passes_quality_gate(features, signal) -> tuple[bool, list[str]]`
- 기능: 품질 게이트 통과 여부 판정.
- 처리 방식: `quality_score`, 유동성, 가격 유효성 검사.

### `app/services/alerts/dedup.py`

#### `build_reason_fingerprint(signal) -> str`
- 기능: 중복 알림 판별용 fingerprint 생성.
- 처리 방식: `direction + signal_type + reason_codes` SHA1(24자리).

#### `is_alert_blocked_by_cooldown(db, instrument, signal) -> bool`
- 기능: cooldown 내 동일 fingerprint 재발송 차단.
- 처리 방식: 최근 `alert_history` 조회 후 시간 비교.

### `app/services/alerts/formatter.py`

#### `format_alert_message(...) -> str`
- 기능: 사용자 알림용 텍스트 포맷팅.
- 처리 방식: 신호/피처/리스크/LLM 요약을 단일 메시지로 구성.

### `app/services/alerts/telegram.py`

#### `class TelegramNotifier`
- 기능: Telegram Bot API 발송.

#### `__init__()`
- 기능: 설정 로드.

#### `send(message) -> dict`
- 기능: 텔레그램 발송.
- 처리 방식: 활성화/토큰 검사 -> `/sendMessage` 호출 -> 상태 dict 반환.
- I/O 예시:
  - 입력: `"[InvestAI] ..."`
  - 출력: `{"status":"sent","http_status":200}` 또는 `{"status":"failed",...}`

### `app/services/llm/gemini_client.py`

#### `class GeminiClient`
- 기능: Gemini 설명 생성 + 실패 fallback.

#### `__init__()`
- 기능: 설정 로드.

#### `_fallback_explanation(signal) -> dict`
- 기능: LLM 실패 시 기본 설명 JSON 생성.

#### `explain_signal(ticker, signal, features) -> dict`
- 기능: Gemini(JSON) 호출 후 설명 반환.
- 처리 방식: `GEMINI_ENABLED` 확인 -> Vertex AI 호출 -> 실패 시 fallback.

## 6) 설정/로깅/DB 세션

### `app/core/config.py`

#### `class Settings`
- 기능: `.env` 기반 설정 모델.
- 처리 방식: `pydantic-settings`로 환경변수 로드.
- 주요 출력: DB, Gemini, Telegram, 외부 API 키 설정값.

#### `credentials_path() -> Path`
- 기능: `GOOGLE_APPLICATION_CREDENTIALS` 절대경로 반환.

#### `get_settings() -> Settings`
- 기능: 설정 싱글톤 반환(`lru_cache`).

### `app/core/logging.py`

#### `configure_logging()`
- 기능: 전역 로거 포맷/레벨 설정.

### `app/db/base.py`

#### `class Base(DeclarativeBase)`
- 기능: SQLAlchemy 모델 베이스 클래스.

### `app/db/session.py`

#### `get_db() -> Generator[Session, None, None]`
- 기능: FastAPI DI용 DB 세션 제공/정리.

## 7) 스키마/모델 클래스

### Pydantic 스키마 클래스
- 파일: `app/schemas/common.py`, `app/schemas/analysis.py`, `app/schemas/ingestion.py`
- 클래스:
  - `HealthResponse`, `SignalReason`, `MarketFeatureSet`, `SignalResult`
  - `AnalyzeTickerRequest`, `AlertPayload`, `AnalyzeTickerResponse`
  - `TickerIngestionRequest`, `XRecentSearchRequest`
  - `InstrumentSearchRequest`, `InstrumentSearchCandidate`, `InstrumentSearchResponse`
  - `IngestionProbeResponse`, `CollectExternalBundleResponse`
- 기능: API 요청/응답 유효성 검증 + OpenAPI 스키마 생성.
- I/O 예시:
  - 입력(JSON) -> Pydantic 객체
  - 출력(Pydantic 객체) -> JSON 직렬화

### SQLAlchemy 모델 클래스
- 파일: `app/db/models.py`
- 클래스:
  - `Instrument`, `PriceDaily`, `NewsParsed`, `DisclosureParsed`, `MacroSnapshot`, `SignalDecision`, `AlertHistory`
- 기능: DB 테이블 매핑 및 저장 구조 정의.

## 8) 워커/검증 스크립트/테스트

### `app/workers/scheduler.py`

#### `build_scheduler() -> BackgroundScheduler`
- 기능: 백그라운드 스케줄러 생성(현재 job 미등록 상태).

### `scripts/run_e2e_pipeline.py`

#### `main() -> int`
- 기능: 파이프라인 E2E 단독 실행.
- 처리 방식: `.env` 로드 -> DB 연결 -> `AnalysisPipeline.run()` 실행 -> 핵심 결과 출력.

### `scripts/verify_postgres.py`

#### `main() -> int`
- 기능: PostgreSQL 연결 확인.
- 처리 방식: `select 1` 성공/실패 코드 반환.

### `scripts/verify_telegram.py`

#### `_run() -> int`
- 기능: Telegram 발송 상태 확인.
- 처리 방식: env 검사 -> `TelegramNotifier.send()` 호출 -> 성공 여부 코드 반환.

### `tests/test_signal_scorer.py`

#### `test_signal_scorer_bullish_case()`
- 기능: 강세 시나리오 점수/품질 검증.

#### `test_signal_scorer_risk_case()`
- 기능: 리스크 시나리오에서 낮은 점수/리스크 플래그 검증.

## 9) 빠른 인수인계 체크리스트

- API 흐름 시작점: `app/api/routes/analysis.py` -> `AnalysisPipeline.run()`
- 종목 식별/수집 이슈: `app/services/ingestion/providers.py`
- 신호 로직 변경 포인트: `app/services/signal/scorer.py`
- 품질 게이트 변경 포인트: `app/services/quality/gates.py`
- 알림 메시지/중복/채널: `app/services/alerts/*`
- LLM 응답 포맷: `app/services/llm/gemini_client.py`
- 스키마 변경 시: `app/schemas/*` + 라우터 응답모델 동시 점검
