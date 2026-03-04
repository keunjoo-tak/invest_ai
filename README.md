# InvestAI Signal & Intelligence Service

FastAPI 기반 투자 인텔리전스 백엔드입니다.  
국내 주식 중심의 종목 분석, 전략 시나리오, 시장 브리프, 문서형 데이터 배치 수집/적재를 제공합니다.

## 1. 서비스 개요
- 핵심 서비스:
  - Stock Insight: 종목 상태/이벤트/기술/수급 요약
  - Trade Compass: 시나리오 기반 대응 전략
  - Market Pulse: 섹터/거시 기반 시장 브리프
- 알림:
  - 텔레그램 채널 지원
  - 임계치/중복방지/강제발송(`force_send`) 정책 지원
- LLM:
  - Gemini 2.5 Pro (ADC) 사용
  - 설명 생성 + 문서 요약 + 한국어 후처리 번역 지원

## 2. 아키텍처
- API Layer: FastAPI 라우터
- Ingestion Layer: API 수집 + 웹 크롤링/파싱 + 배치 수집
- Processing Layer: 정규화/중복방지/엔터티 연결/이벤트 분류/점수화
- Intelligence Layer: Feature/Signal/Scenario/Regime 엔진
- Storage Layer: PostgreSQL + 로컬 원문 아카이브(`downloads/`)
- Delivery Layer: Telegram 알림

## 2.1 전체 아키텍처 도식
```mermaid
flowchart LR
  U[User / Admin / Scheduler] --> API[FastAPI API Layer]
  API --> ING[Ingestion Layer]
  ING --> PROC[Processing & Enrichment]
  PROC --> INTEL[Intelligence Engines]
  INTEL --> API

  ING --> RAW[(downloads Raw Archive)]
  PROC --> DB[(PostgreSQL)]
  INTEL --> DB
  API --> NOTI[Telegram Notifier]

  EXT1[KIS/NAVER/DART/X] --> ING
  EXT2[KRX KIND/Policy Briefing/BOK] --> ING
  LLM[Gemini 2.5 Pro ADC] --> PROC
  LLM --> INTEL
```

## 2.2 서비스별 I/O 개요
| 서비스 | 주요 입력(I) | 핵심 처리 | 주요 출력(O) |
|---|---|---|---|
| Stock Insight | 종목명/티커, 기준일 | 수집 -> 피처 -> 신호 -> 요약 | 상태라벨, 이벤트/리스크, 체크포인트 |
| Trade Compass | 종목, 투자성향, 목적, 보유정보 | Insight 재사용 + 가격대/시나리오 계산 | 권장행동, 진입/무효화/목표 구간, 시나리오 |
| Market Pulse | 기준일 | 유니버스/섹터 집계 + 체제 분류 + 문서요약 반영 | 시장진단, 강약 섹터, 전략 힌트 |
| Analyze Pipeline | 종목, 알림옵션, 언어 | 원문저장 + LLM요약 + 신호/알림판정 + DB적재 | features/signal/explanation/alert |
| Batch Ingestion | 소스별 배치 파라미터 | 수집 -> 파싱/표준화 -> 요약 -> external_document upsert | fetched/stored/skipped, 저장경로 |

## 2.3 서비스별 처리 흐름 도식
### Stock Insight
```mermaid
flowchart TD
  A[Input: ticker_or_name, as_of_date] --> B[Symbol Resolve]
  B --> C[Collect Price/News/Disclosure/Macro]
  C --> D[Build Features]
  D --> E[Evaluate Signal + Quality Gate]
  E --> F[LLM Explain]
  F --> G[Merge external_document briefs]
  G --> H[Output: StockInsightResponse]
```

### Trade Compass
```mermaid
flowchart TD
  A[Input: ticker_or_name, risk_profile, objective] --> B[Run Stock Insight]
  B --> C[Derive Action by score/risk_profile]
  C --> D[Compute Buy/Invalidation/Target Zones]
  D --> E[Generate Bull/Base/Bear Scenarios]
  E --> F[Output: TradeCompassResponse]
```

### Market Pulse
```mermaid
flowchart TD
  A[Input: as_of_date] --> B[Collect universe price snapshots]
  B --> C[Sector aggregation]
  C --> D[Regime classification]
  D --> E[Load policy/BOK docs from external_document]
  E --> F[Build strategy hints]
  F --> G[Output: MarketPulseOverviewResponse]
```

### Analyze/Ticker 통합 파이프라인
```mermaid
flowchart TD
  A[POST analyze/ticker] --> B[Resolve instrument]
  B --> C[Fetch KIS/NAVER/DART/Macro]
  C --> D[Save raw docs to downloads call-dir]
  D --> E[Preprocess + LLM summarize_documents]
  E --> F[Persist parsed data tables]
  F --> G[Build features + signal + explanation]
  G --> H[Alert decision threshold/cooldown/force_send]
  H --> I[Telegram send attempt]
  I --> J[Persist signal_decision + alert_history]
  J --> K[Output AnalyzeTickerResponse]
```

### 문서형 배치 파이프라인 (KIND/정책브리핑/BOK)
```mermaid
flowchart TD
  A[Batch Trigger API or Scheduler] --> B[Seed URL collection]
  B --> C[Link extraction + document fetch]
  C --> D[Raw save metadata/content/raw file]
  D --> E[Normalize + event/entity/score]
  E --> F[LLM summarize_documents]
  F --> G[Upsert external_document]
  G --> H[Output BatchIngestionResponse]
```

## 3. 주요 엔드포인트 (전체)
모든 엔드포인트는 기본 prefix ` /api/v1 `를 사용합니다.

### GET `/api/v1/health`
- 개요: 서버 상태와 실행 환경 정보를 반환합니다.
- 입력: 없음
- 출력: `status`, `app`, `env`, `time_utc`
- 처리 로직: 환경 설정 로드 후 현재 UTC 시각을 포함한 헬스 응답 반환

### POST `/api/v1/analyze/ticker`
- 개요: 종목 단위 통합 분석 + 신호 판정 + 설명 생성 + 알림 판단을 수행합니다.
- 입력:
- `ticker_or_name`, `as_of_date`, `lookback_days`, `analysis_mode`
- `notify`, `force_send`, `channels`, `response_language`
- 출력:
- `features`, `signal`, `explanation`, `alert`
- `alert.channel_results.telegram.status/status_code/reason/reason_code`
- 처리 로직:
- 종목 식별 -> 시세/뉴스/공시/매크로 수집
- 원문 다운로드/저장(`downloads/`) + 문서 요약(LLM)
- 피처 생성 -> 신호 평가 -> 품질 게이트
- 알림 임계치/쿨다운/강제발송 정책 평가
- DB 적재(`price_daily`, `news_parsed`, `disclosure_parsed`, `macro_snapshot`, `signal_decision`, `alert_history`)

### GET `/api/v1/stock-insight/{ticker_or_name}`
- 개요: 종목 상태를 투자 해석 중심으로 반환합니다.
- 입력:
- Path: `ticker_or_name`
- Query: `as_of_date`(옵션)
- 출력:
- `one_line_diagnosis`, `state_label`, `valuation_summary`
- `event_summary`, `flow_summary`, `technical_summary`, `risk_factors`, `checkpoints`
- 처리 로직:
- 분석 코어 재사용(수집/피처/신호/LLM 설명)
- `external_document` 최신 문서 요약을 이벤트 설명에 병합

### POST `/api/v1/trade-compass/analyze`
- 개요: 종목 분석 결과를 시나리오 기반 대응 전략으로 변환합니다.
- 입력:
- `ticker_or_name`, `investment_horizon`, `risk_profile`, `objective`
- `has_position`, `avg_buy_price`, `response_language`
- 출력:
- `recommended_action`, `confidence_band`
- `buy_interest_zone`, `invalidation_zone`, `target_zone_primary`, `target_zone_secondary`
- `scenarios`, `reasoning`, `source_insight`
- 처리 로직:
- Stock Insight 호출
- 점수/리스크 성향 기반 액션/가격대 산출
- 상승/기본/하락 시나리오 생성

### GET `/api/v1/market-pulse/overview`
- 개요: 시장 체제/섹터 강약/전략 힌트를 제공합니다.
- 입력:
- Query: `as_of_date`(옵션)
- 출력:
- `market_one_line`, `regime`, `regime_score`
- `strong_sectors`, `weak_sectors`, `macro_summary`, `strategy_hints`, `representative_symbols`
- 처리 로직:
- 유니버스 수익률/변동성 집계
- 섹터 점수/시장 체제 분류
- 정책브리핑/한국은행 적재 문서(`external_document`) 요약을 전략 힌트에 반영

### GET `/api/v1/ingestion/sources/catalog`
- 개요: 데이터소스 카탈로그를 조회합니다.
- 입력: 없음
- 출력: `source_id`, `name`, `category`, `url`, `collection_mode`, `parser_required`
- 처리 로직: 정적 카탈로그(`source_catalog.py`) 반환

### POST `/api/v1/ingestion/crawl/preview`
- 개요: 지정 소스를 크롤링/파싱해 전처리 결과를 미리 확인합니다.
- 입력: `source_id`, `target_url`(옵션), `max_chars`
- 출력:
- `fetched_url`, `http_status`, `content_type`, `content_length`, `sample_text`
- `parsed`(entities/event_type/scores/fingerprint/version)
- 처리 로직: URL fetch -> 텍스트 정리 -> 엔터티/이벤트/점수화 -> 파싱 결과 반환

### POST `/api/v1/ingestion/crawl/collect`
- 개요: 크롤링 결과를 호출 단위 폴더에 저장합니다.
- 입력: `source_id`, `target_url`(옵션), `request_label`, `max_chars`
- 출력: `saved_call_dir`, `saved_paths`, `parsed`
- 처리 로직:
- preview 실행
- `downloads/{request_label}_{UTC}_{request_id}` 생성
- `metadata.json`, `content.txt`, `raw.*`, snapshot 저장

### POST `/api/v1/batch/kind/disclosures`
- 개요: KIND 공시(정기/수시) 배치를 수집/처리/적재합니다.
- 입력: `ticker_or_name`, `max_items`
- 출력: `fetched_count`, `stored_count`, `skipped_count`, `saved_call_dir`
- 처리 로직:
- 종목 식별 -> 공시 원문 수집/저장 -> 전처리/LLM 요약
- `external_document` upsert(중복은 skip)

### POST `/api/v1/batch/policy-briefing`
- 개요: 정책브리핑(청와대/국무회의/부처브리핑/정책뉴스) 배치 적재를 수행합니다.
- 입력: `max_items`
- 출력: `fetched_count`, `stored_count`, `skipped_count`, `saved_call_dir`
- 처리 로직:
- seed URL 수집 -> 링크 추출 -> 본문 파싱/저장 -> LLM 요약
- `external_document` upsert

### POST `/api/v1/batch/bok/publications`
- 개요: 한국은행 자료(간행물/조사연구/지역/국외/업무별정보) 배치 적재를 수행합니다.
- 입력: `max_items`
- 출력: `fetched_count`, `stored_count`, `skipped_count`, `saved_call_dir`
- 처리 로직:
- seed URL 수집 -> 링크 추출 -> 본문 파싱/저장 -> LLM 요약
- `external_document` upsert

### POST `/api/v1/internal/jobs/recompute-features`
- 개요: 피처 재계산 작업 트리거 샘플
- 입력: 없음
- 출력: `status`, `macro_rows`
- 처리 로직: 매크로 스냅샷 조회 건수 반환(샘플)

### POST `/api/v1/internal/ingestion/instrument/resolve`
- 개요: 종목명/티커를 정규화해 매핑 결과를 확인
- 입력: `ticker_or_name`
- 출력: `details.ticker/name_kr/market/sector`
- 처리 로직: 종목 식별기(`resolve_instrument`) 호출

### POST `/api/v1/internal/ingestion/instrument/search`
- 개요: 종목 후보 검색(자연어/부분티커)
- 입력: `query`, `limit`
- 출력: `candidates[]`(ticker, name_kr, score, match_type, corp_code)
- 처리 로직: 텍스트 유사도 + 별칭 매핑으로 후보 정렬

### POST `/api/v1/internal/ingestion/price/kis/daily`
- 개요: KIS 일봉 수집 진단
- 입력: `ticker_or_name`, `as_of_date`, `lookback_days`
- 출력: 일봉 샘플 + base URL 선택 정보
- 처리 로직: KIS 토큰 발급/일봉 조회 호출 결과 확인

### POST `/api/v1/internal/ingestion/news/naver`
- 개요: NAVER 뉴스 수집 진단
- 입력: `ticker_or_name`, `max_items`
- 출력: 뉴스 샘플(제목/URL/발행시각)
- 처리 로직: NAVER 검색 API 호출 결과 확인

### POST `/api/v1/internal/ingestion/disclosures/dart/corp-code-map`
- 개요: DART corp_code 매핑 진단
- 입력: `ticker_or_name`
- 출력: `corp_code`, `mapping_size`
- 처리 로직: corpCode.xml 파싱 캐시 조회

### POST `/api/v1/internal/ingestion/disclosures/dart/list`
- 개요: DART 공시 목록 수집 진단
- 입력: `ticker_or_name`, `as_of_date`, `days`
- 출력: 공시 샘플(공시ID/제목/발행시각)
- 처리 로직: OPENDART list API 호출

### POST `/api/v1/internal/ingestion/macro/snapshot`
- 개요: 매크로 입력 데이터 진단
- 입력: `as_of_date`
- 출력: 매크로 샘플
- 처리 로직: 현재 매크로 데이터 공급 경로 확인

### POST `/api/v1/internal/ingestion/social/x/recent-search`
- 개요: X Recent Search 진단
- 입력: `query`, `max_results`
- 출력: HTTP 상태/에러 정보/샘플 tweet
- 처리 로직: X API 토큰 검증 + recent search 호출

### POST `/api/v1/internal/ingestion/collect-external-bundle`
- 개요: 외부 수집 번들(KIS/NAVER/DART/매크로) 일괄 진단
- 입력: `ticker_or_name`, `as_of_date`, `lookback_days`, `max_items`, `days`
- 출력: 소스별 `IngestionProbeResponse` 배열
- 처리 로직: 각 수집기를 한 번에 실행하고 성공/건수/샘플 집계

## 4. 환경 변수
필수/권장 변수:
- 공통
  - `DATABASE_URL` (예: `postgresql+psycopg://postgres:0000@localhost:5432/postgres`)
  - `DOWNLOADS_DIR` (기본 `downloads`)
- Gemini (ADC)
  - `GOOGLE_APPLICATION_CREDENTIALS`
  - `GEMINI_PROJECT_ID`
  - `GEMINI_LOCATION`
  - `GEMINI_MODEL`
  - `GEMINI_ENABLED`
- Telegram
  - `TELEGRAM_ENABLED`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- 외부 데이터 소스
  - `KIS_APP_KEY`, `KIS_APP_SECRET`
  - `KIS_BASE_URL`, `KIS_PROD_BASE_URL`, `KIS_MOCK_BASE_URL`
  - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
  - `DART_API_KEY`
  - `X_BEARER_TOKEN`

## 5. 실행 방법
```powershell
py -m uvicorn app.main:app --host 127.0.0.1 --port 5000 --reload
```
- Swagger: `http://127.0.0.1:5000/docs`
- 웹 대시보드: `http://127.0.0.1:5000/app`

## 5.1 웹 화면(운영 콘솔)
- 경로: `GET /app`
- 정적 자산:
  - `/assets/styles.css`
  - `/assets/app.js`
- UI 기능:
  - 종목 통합 분석 실행 (`/api/v1/analyze/ticker`)
  - Stock Insight 조회 (`/api/v1/stock-insight/{ticker}`)
  - Trade Compass 전략 생성 (`/api/v1/trade-compass/analyze`)
  - Market Pulse 조회 (`/api/v1/market-pulse/overview`)
  - 문서 수집 미리보기 (`/api/v1/ingestion/crawl/preview`)
  - KIND/정책브리핑/BOK 배치 실행 (`/api/v1/batch/*`)

## 6. 분석 API 사용 예시
`POST /api/v1/analyze/ticker`

```json
{
  "ticker_or_name": "005930",
  "analysis_mode": "full",
  "notify": true,
  "force_send": false,
  "channels": ["telegram"],
  "response_language": "ko"
}
```

응답의 알림 필드:
- `should_send`: 최종 발송 여부
- `channel_results.telegram.status`: 한글 상태
- `channel_results.telegram.status_code`: 내부 상태 코드(`sent/skipped/blocked/failed`)
- `channel_results.telegram.reason`: 한글 사유
- `channel_results.telegram.reason_code`: 내부 사유 코드

## 7. 원문 저장/요약 처리 구조
분석 및 수집 호출 시 원문을 `downloads/`에 호출 단위로 저장합니다.

- 저장 경로 예시:
  - `downloads/analyze_ticker_{UTC}_{request_id}/...`
  - `downloads/{request_label}_{UTC}_{request_id}/...`
- 문서 단위 저장 파일:
  - `metadata.json`
  - `content.txt`
  - `raw.*` (html/pdf/doc/hwp 등)
- 처리 흐름:
  1. 수집(API/웹)
  2. 전처리(정규화/엔터티/이벤트/점수화)
  3. LLM 문서 요약
  4. DB 적재 + 인텔리전스 응답 반영

## 8. 데이터 수집/활용 현황
수집 상태:
- `운영`: 실제 수집/적재 동작 중
- `부분`: 일부 진단/수동 수집만 가능
- `예정`: 설계 반영, 미구현

| 데이터 영역 | 수집 소스 | 소스 ID | 수집 상태 | 활용 상태 | 비고 |
|---|---|---|---|---|---|
| 종목 마스터 | OpenDART corpCode | S05 | 운영 | 운영 | 종목 식별/매핑 |
| 일봉 시세 | KIS API | S01 | 운영 | 운영 | 실패 시 fallback |
| 뉴스 메타/원문 | NAVER + 기사 원문 | S08 | 운영 | 운영 | 원문 요약 반영 |
| 공시 메타/원문 | OpenDART + DART 문서 | S05 | 운영 | 운영 | 원문 요약 반영 |
| 매크로 스냅샷 | 내부 샘플 | 내부 | 부분 | 운영 | 향후 ECOS 대체 |
| X 검색 | X API v2 | S12 | 부분 | 부분 | 프로브 중심 |
| KIND 공시 배치 | KRX KIND 지향 수집 | S06 | 운영 | 운영 | 정기/수시 분류 적재 |
| 정책브리핑 배치 | 정책브리핑 웹 | S28 | 운영 | 운영 | 청와대/국무회의/부처/정책뉴스 |
| 한국은행 배치 | 한국은행 웹 | S16 | 운영 | 운영 | 간행물/조사연구/지역/국외/업무별 |
| 미국 공시/XBRL | SEC EDGAR | S26 | 예정 | 예정 | 2단계 확장 |

## 9. 배치 적재 파이프라인
- KIND 공시 배치:
  - `POST /api/v1/batch/kind/disclosures`
- 정책브리핑 배치:
  - `POST /api/v1/batch/policy-briefing`
- 한국은행 배치:
  - `POST /api/v1/batch/bok/publications`

스케줄러:
- 정책브리핑: 매일 06:15
- 한국은행: 매일 06:35

## 10. PostgreSQL public 스키마 테이블(8개)
현재 운영 테이블:
- `instrument_master`
- `price_daily`
- `news_parsed`
- `disclosure_parsed`
- `macro_snapshot`
- `signal_decision`
- `alert_history`
- `external_document`

테이블별 용도/적재:
- `instrument_master`: 종목 마스터. 분석/배치 시 종목 식별 단계에서 생성/갱신
- `price_daily`: 일봉 OHLCV. 분석 파이프라인 수집 데이터 적재
- `news_parsed`: 뉴스 메타/감성/요약. 분석 파이프라인 적재
- `disclosure_parsed`: 공시 메타/이벤트/요약. 분석 파이프라인 적재
- `macro_snapshot`: 거시 스냅샷. 분석 파이프라인 적재
- `signal_decision`: 신호 점수/근거/리스크. 분석 결과 적재
- `alert_history`: 알림 발송 이력/중복방지 추적
- `external_document`: KIND/정책브리핑/한국은행 문서 통합 적재(배치)

코멘트(description):
- 8개 테이블의 table/column comment를 실제 DB에 반영 완료

## 11. 저장소 구조
```text
app/
  api/routes/
  core/
  db/
  schemas/
  services/
    alerts/
    features/
    ingestion/
    intelligence/
    llm/
    pipeline/
    quality/
    signal/
  workers/
scripts/
sql/
tests/
downloads/ (runtime)
```

## 12. 검증 상태
- `py -m compileall app` 성공
- `py -m pytest -q tests` 통과
- 주요 API 실호출 200 확인
- 배치 엔드포인트(KIND/정책브리핑/한국은행) 실호출 확인
