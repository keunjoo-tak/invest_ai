# 데이터 자산 문서

## 1. 문서 목적
이 문서는 현재 프로젝트에서 수집, 정제, 저장, 재사용하는 모든 데이터 자산을 한눈에 식별할 수 있도록 정리한 문서다.  
각 데이터에 대해 다음 내용을 함께 기록한다.

- 원천 소스는 어디인지
- 원천 데이터가 어떤 의미를 가지는지
- 서비스에서 왜 사용하는지
- 어떤 전처리와 정규화를 거치는지
- 최종적으로 어디에 저장되는지
- 어떤 서비스와 화면에서 사용되는지

이 문서는 `README.md`의 개요 문서가 아니라, 실제 데이터 자산과 데이터 흐름을 기준으로 작성한 운영 문서다.

## 2. 데이터 흐름 요약
현재 데이터 흐름은 크게 다섯 단계로 나뉜다.

1. 원천 수집
2. 원문 또는 원본 파일 보존
3. 텍스트/수치 정제 및 표준화
4. 특징값(feature)과 제품용 요약 정보 생성
5. 사용자 제품, 배치 문서, 알림에 재사용

주요 흐름은 다음과 같다.

```text
원천 API/크롤러
-> SourceProviderClient / BatchIngestor
-> RawArchiveManager 로컬 보관
-> preprocessing.py 정제 / Gemini 요약·신호추출
-> DB 적재
-> feature_builder.py 특징값 생성
-> AnalysisPipeline / DecisionProductService
-> 웹 리포트 / Swagger 응답 / 텔레그램 알림
```

## 3. 데이터 자산 분류
현재 프로젝트의 데이터는 아래 범주로 관리된다.

- 종목 기준 데이터
  - 종목 마스터
  - 가격 일봉
  - 종목 뉴스
  - 공시
  - 재무제표
- 시장 및 거시 데이터
  - 국내 거시
  - 미국 거시
  - 국제 거시
  - 공식 이벤트 일정
  - 글로벌 이슈 스트림
- 문서형 데이터
  - 정책브리핑
  - 한국은행 자료
  - KIND 공시 문서
  - 글로벌 거시 브리핑 문서
  - 국제 거시 브리핑 문서
- 파생/내부 데이터
  - 텍스트 구조화 결과
  - 신호 및 점수
  - 시장 체제 스냅샷
  - 워치리스트 및 알림 이력
  - 로컬 원문 아카이브

## 4. 원천 데이터 상세

### 4.1 종목 마스터 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 종목 마스터 |
| 원천 소스 | OpenDART `corpCode.xml`, 내부 fallback 카탈로그 |
| 원천 데이터 설명 | 상장사 종목코드, 회사명, DART 법인코드 매핑 정보 |
| 서비스 활용 용도 | 종목명 입력을 티커로 정규화하고, 공시/재무제표 조회의 기준키로 사용 |
| 전처리 방식 | 종목코드 6자리 정규화, 종목명 소문자 비교, fallback 카탈로그와 병합 |
| 저장 위치 | `instrument_master` |
| 주요 사용 서비스 | `Stock Decision`, `Action Planner`, `Watchlist Alerts`, `Analyze Ticker` |

추가 설명
- 종목명 또는 티커를 입력받으면 `SourceProviderClient.resolve_instrument()`가 가장 먼저 실행된다.
- OpenDART 법인코드 맵은 공시, 재무제표 API 조회를 위해 필수 키로 사용된다.
- 일부 대표 종목은 fallback 카탈로그에도 들어 있어 DART 실패 시 기본 동작을 유지한다.

### 4.2 가격 일봉 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 일봉 시세 |
| 원천 소스 | 한국투자증권 KIS API |
| 원천 데이터 설명 | 거래일별 시가, 고가, 저가, 종가, 거래량 |
| 서비스 활용 용도 | 추세, 변동성, 거래량, RSI, 수익률, ATR 등 가격 기반 특징 생성 |
| 전처리 방식 | 숫자형 변환, 날짜 정규화, 최근 구간 슬라이싱, 중복 거래일 제거 |
| 저장 위치 | `price_daily` |
| 주요 사용 서비스 | `Market Regime`, `Stock Decision`, `Action Planner`, `Analyze Ticker` |

생성되는 대표 파생값
- `ma_20`, `ma_60`
- `rsi_14`
- `volatility_20d`
- `atr_14_pct`
- `return_1d`, `return_5d`, `return_20d`
- `gap_return_1d`
- `rel_volume`
- `turnover_value_zscore`

### 4.3 국내 종목 뉴스 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 국내 뉴스 |
| 원천 소스 | Naver News API |
| 원천 데이터 설명 | 종목 관련 기사 제목, 링크, 발행 시각, 요약에 가까운 본문 정보 |
| 서비스 활용 용도 | 이벤트 감지, 감성 점수, 주목도, 종목·섹터 관련 단기 촉매 해석 |
| 전처리 방식 | HTML 제거, 원문 추가 수집, 본문 정제, 키워드 기반 이벤트 분류, LLM 요약/신호추출 |
| 저장 위치 | `news_parsed`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Stock Decision`, `Action Planner`, `Watchlist Alerts`, `Analyze Ticker` |

실제 전처리 내용
- `html_cleaner()`로 태그 제거
- `normalize_text_for_storage()`로 제어문자 제거
- `enrich_news_records()`로 아래 필드 생성
  - `sentiment_score`
  - `impact_score`
  - `freshness_score`
  - `event_type`
  - `keyword_density`
  - `supply_signal`
  - `financing_risk`
  - `governance_signal`
  - `shareholder_return_signal`
  - `attention_score`
  - `entities`

### 4.4 글로벌 뉴스 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 글로벌 뉴스 |
| 원천 소스 | NewsAPI |
| 원천 데이터 설명 | 종목 영문명, 시장 키워드, 글로벌 매크로 키워드 기반 기사 |
| 서비스 활용 용도 | 미국/글로벌 뉴스 흐름, 국제 정책/거시 이슈, 해외 투자심리 보조 신호 |
| 전처리 방식 | 기사 URL 추가 본문 수집, 원문 텍스트 정제, LLM 요약, 거시 이벤트 텍스트화 |
| 저장 위치 | 분석 응답 내부, `macro_snapshot` 일부 파생행, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Market Regime`, `Stock Decision`, `Analyze Ticker` |

추가 설명
- 종목 단위 뉴스로도 사용하고, 거시 뉴스의 경우 `fetch_macro()` 내부에서 거시 보조 신호로도 사용한다.
- 단순 헤드라인 나열이 아니라, 시장 민감 키워드를 포함한 뉴스 묶음을 정량형 보조 신호로 바꿔 사용한다.

### 4.5 공시 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 종목 공시 |
| 원천 소스 | OpenDART 공시 목록 API |
| 원천 데이터 설명 | 공시 제목, 접수번호, 접수일, 공시 문서 링크 |
| 서비스 활용 용도 | 실적, 자금조달, 공급계약, 주주환원, 지배구조 등 이벤트 해석 |
| 전처리 방식 | DART 법인코드 매핑, 공시 제목/본문 수집, 이벤트 분류, 영향점수 계산, LLM 신호추출 |
| 저장 위치 | `disclosure_parsed`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Stock Decision`, `Action Planner`, `Watchlist Alerts`, `Analyze Ticker` |

실제 전처리 내용
- `event_classifier()`로 1차 이벤트 유형 분류
- `enrich_disclosure_records()`로 아래 필드 생성
  - `impact_score`
  - `sentiment_score`
  - `freshness_score`
  - `supply_signal`
  - `financing_risk`
  - `shareholder_return_signal`
  - `governance_signal`
  - `earnings_event_flag`
  - `contract_event_flag`
  - `financing_event_flag`
  - `shareholder_return_event_flag`
  - `governance_event_flag`

### 4.6 KIND 공시 문서 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | KIND 공시 문서 |
| 원천 소스 | KRX KIND |
| 원천 데이터 설명 | 수시공시, 정기공시, IR 성격의 문서형 공시 |
| 서비스 활용 용도 | 외부 문서 저장, 공시 원문 보존, 문서 기반 투자 근거 강화 |
| 전처리 방식 | 문서 다운로드, 제목/본문 정제, KIND 유형 분류, LLM 요약, 시장 관련성 선별 |
| 저장 위치 | `external_document`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | 운영자 배치, 문서형 투자 근거, 향후 종목 리포트 근거 확장 |

### 4.7 재무제표 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 재무제표 |
| 원천 소스 | OpenDART `fnlttSinglAcntAll.json` |
| 원천 데이터 설명 | 손익계산서, 재무상태표, 현금흐름표 주요 계정 |
| 서비스 활용 용도 | 수익성, 성장성, 재무안정성, 현금흐름 품질 평가 |
| 전처리 방식 | 최신 보고서 선택, 계정명 매핑, 비율형 재무 feature 계산, 요약 텍스트 생성 |
| 저장 위치 | 분석 응답 내부 JSON, 로컬 스냅샷 파일 |
| 주요 사용 서비스 | `Stock Decision`, `Action Planner`, `Analyze Ticker` |

생성되는 대표 재무 feature
- `revenue_growth_yoy`
- `operating_margin`
- `net_margin`
- `debt_ratio`
- `current_ratio`
- `operating_cashflow_margin`

## 5. 국내 거시 데이터

### 5.1 한국은행 ECOS

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 국내 거시 핵심지표 |
| 원천 소스 | 한국은행 ECOS OpenAPI |
| 원천 데이터 설명 | 환율, 금리, 통화량, 채권금리 등 국내 금융·거시 지표 |
| 서비스 활용 용도 | 국내 유동성, 금리 압력, 환율 부담 등 시장 체제 판단 |
| 전처리 방식 | 지표별 최신값과 이전값 비교, 방향 해석, surprise 유사 점수화 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Stock Decision`, `Analyze Ticker` |

대표 지표 예시
- 원/달러 환율
- KOSPI
- 국고채 3년
- 회사채 3년 AA-
- M2

### 5.2 KOSIS

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 국내 통계 데이터 |
| 원천 소스 | KOSIS OpenAPI |
| 원천 데이터 설명 | 소비자물가, 실업, 산업생산, 수출 관련 국가통계 |
| 서비스 활용 용도 | 국내 경기와 물가 국면 보조 판단 |
| 전처리 방식 | 테이블 검색 결과를 표준 거시 행으로 정리하고, 발표 최신성/커버리지 신호로 변환 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Analyze Ticker` |

## 6. 미국 및 글로벌 거시 데이터

### 6.1 FRED

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 미국 금리·시장 지표 |
| 원천 소스 | FRED API |
| 원천 데이터 설명 | 연준 기준금리, 미국채 금리 등 시계열 데이터 |
| 서비스 활용 용도 | 미국 금리 압력, 할인율 환경, 위험선호 변화 판단 |
| 전처리 방식 | 최신 관측치와 직전값 비교, 방향성 해석, 리스크/지원 점수화 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Stock Decision`, `Analyze Ticker` |

### 6.2 BLS

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 미국 물가·고용 지표 |
| 원천 소스 | BLS API |
| 원천 데이터 설명 | CPI, PPI, 실업률, 고용 관련 통계 |
| 서비스 활용 용도 | 인플레이션 재가속, 노동시장 둔화, 정책 부담 판단 |
| 전처리 방식 | 시계열 최신값 정규화, 이전치 비교, 발표 일정과 연결 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Analyze Ticker` |

### 6.3 BEA

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 미국 성장·소비 지표 |
| 원천 소스 | BEA API |
| 원천 데이터 설명 | GDP, PCE 물가 등 미국 실물경제·소비 지표 |
| 서비스 활용 용도 | 미국 경기 방향과 소비 기반 강도 판단 |
| 전처리 방식 | 표 데이터에서 필요한 line만 추출하고 시계열로 정리 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Analyze Ticker` |

### 6.4 Fiscal Data

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 미국 재정 데이터 |
| 원천 소스 | U.S. Treasury Fiscal Data API |
| 원천 데이터 설명 | 국가부채, 재정수지 등 미국 재정 관련 수치 |
| 서비스 활용 용도 | 장기 금리 부담, 재정 압력, 위험 프리미엄 보조 판단 |
| 전처리 방식 | 최신값과 이전값 차이 계산, 재정 압력 해석 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Analyze Ticker` |

### 6.5 OECD

| 항목 | 내용 |
| --- | --- |
| 데이터명 | OECD 국제 거시 지표 및 브리핑 |
| 원천 소스 | OECD API, OECD 뉴스룸/피드 |
| 원천 데이터 설명 | 회원국 물가, 경기, 정책 관련 통계 및 브리핑성 자료 |
| 서비스 활용 용도 | 국제 경기 방향과 유럽/선진국 물가 흐름 판단 |
| 전처리 방식 | 수치 시계열 정리 + 브리핑 문서형 스냅샷 생성 |
| 저장 위치 | `macro_snapshot`, `external_document` |
| 주요 사용 서비스 | `Market Regime`, 글로벌 거시 배치 |

### 6.6 World Bank

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 국제 개발·성장 지표 |
| 원천 소스 | World Bank API |
| 원천 데이터 설명 | 성장률, 물가 등 국가 단위 거시 지표 |
| 서비스 활용 용도 | 국제 경기 보조 판단, 유럽 및 주요국 거시 배경 보강 |
| 전처리 방식 | 국가/지표별 최신값 수집, 표준 거시 행으로 정규화 |
| 저장 위치 | `macro_snapshot`, `external_document` |
| 주요 사용 서비스 | 국제 거시 배치, `Market Regime`, `Analyze Ticker` |

### 6.7 IMF

| 항목 | 내용 |
| --- | --- |
| 데이터명 | IMF 국제 거시 지표 |
| 원천 소스 | IMF DataMapper API |
| 원천 데이터 설명 | 국가 및 지역 단위 성장, 물가, 거시 지표 |
| 서비스 활용 용도 | 글로벌 물가와 성장 흐름의 상위 관점 보강 |
| 전처리 방식 | 기간 파싱, 최신값 정규화, 국제 거시 스냅샷 문서화 |
| 저장 위치 | `macro_snapshot`, `external_document` |
| 주요 사용 서비스 | 국제 거시 배치, `Market Regime`, `Analyze Ticker` |

### 6.8 Eurostat

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 유럽 경제통계 |
| 원천 소스 | Eurostat API |
| 원천 데이터 설명 | 유로존 물가, 실업, 산업생산 등 유럽 통계 |
| 서비스 활용 용도 | 유럽 경기/물가 방향, 글로벌 위험선호 보조 판단 |
| 전처리 방식 | API 응답을 시계열로 변환하고 표준 거시 행으로 정리 |
| 저장 위치 | `macro_snapshot`, `external_document` |
| 주요 사용 서비스 | 국제 거시 배치, `Market Regime`, `Analyze Ticker` |

## 7. 이벤트 일정 및 글로벌 이슈 데이터

### 7.1 공식 이벤트 캘린더

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 공식 이벤트 일정 |
| 원천 소스 | Fed, ECB, Eurostat, NBS, BLS, BEA 공개 일정 페이지/피드 |
| 원천 데이터 설명 | 통계 발표, 정책회의, 일정성 이벤트 |
| 서비스 활용 용도 | 미래 이벤트 리스크 파악, 발표 전후 경계구간 인식 |
| 전처리 방식 | 일정 HTML/ICS/RSS 파싱, UTC 시각 정규화, 이벤트 코드 생성 |
| 저장 위치 | `release_calendar_event` |
| 주요 사용 서비스 | `Market Regime`, `Analyze Ticker`, 운영 배치 |

주요 필드
- `source_system`
- `event_code`
- `category`
- `scheduled_at_utc`
- `release_at_utc`
- `available_at_utc`
- `country`

### 7.2 글로벌 이슈 스트림

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 글로벌 이슈 스트림 |
| 원천 소스 | GDELT, ECB RSS, Fed Press Release |
| 원천 데이터 설명 | 국제 시장에 영향을 주는 광역 이슈, 정책 발표, 공식 보도 |
| 서비스 활용 용도 | 글로벌 이벤트·정책성 헤드라인 감지, 리스크온/리스크오프 보조 판단 |
| 전처리 방식 | lookback 기간 기사 수집, 본문 정제, 문서형 적재, 관련성 선별 |
| 저장 위치 | `external_document`, 일부 거시 파생 신호 |
| 주요 사용 서비스 | `Market Regime`, 운영 배치, 문서 미리보기 |

## 8. 문서형 데이터

### 8.1 정책브리핑 문서

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 정책브리핑 문서 |
| 원천 소스 | 정책브리핑 사이트의 정책뉴스, 대통령실, 국무회의, 부처 브리핑 |
| 원천 데이터 설명 | 정부 정책, 산업 지원, 규제, 예산, 제도 변경 관련 문서 |
| 서비스 활용 용도 | 정책 변화가 업종/개별 종목에 주는 영향 분석 근거 |
| 전처리 방식 | 실제 상세 링크만 수집, 본문 블록 추출, 첨부/메타 정리, 시장 관련성 선별, LLM 요약 |
| 저장 위치 | `external_document`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Market Regime`, 문서 기반 인텔리전스, 운영 배치 |

시장 관련성 선별
- 1차: 정책/산업 키워드 휴리스틱
- 2차: Gemini `triage_market_documents`
- 최종: `summary_json`, `metadata_json.triage`, `metadata_json.prediction_signal` 저장

### 8.2 한국은행 문서

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 한국은행 간행물/연구자료 |
| 원천 소스 | 한국은행 RSS 및 상세 페이지, 첨부 PDF/DOCX |
| 원천 데이터 설명 | 간행물, 조사연구, 지역연구자료, 국외사무소자료, 업무별 정보 |
| 서비스 활용 용도 | 통화정책, 경기판단, 금융안정 관점의 문서형 근거 확보 |
| 전처리 방식 | RSS 기반 실제 발행문서 식별, 본문/첨부 추출, PDF/DOCX 텍스트화, 시장 관련성 선별, LLM 요약 |
| 저장 위치 | `external_document`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Market Regime`, 문서 기반 인텔리전스, 운영 배치 |

### 8.3 글로벌 거시 브리핑 문서

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 글로벌 거시 브리핑 문서 |
| 원천 소스 | FRED, BLS, BEA, Fiscal Data, OECD |
| 원천 데이터 설명 | 미국 및 글로벌 거시지표를 문서형 스냅샷으로 재구성한 내부 산출물 |
| 서비스 활용 용도 | 숫자만이 아니라 텍스트형 근거 문서로 거시 판단을 제공 |
| 전처리 방식 | 거시 행 목록을 사람이 읽을 수 있는 브리핑 텍스트로 렌더링 |
| 저장 위치 | `external_document`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Market Regime`, 배치 실행, 운영 문서 확인 |

### 8.4 국제 거시 브리핑 문서

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 국제 거시 브리핑 문서 |
| 원천 소스 | World Bank, IMF, Eurostat |
| 원천 데이터 설명 | 국제/유럽 거시지표를 요약한 내부 스냅샷 문서 |
| 서비스 활용 용도 | 국제 경기와 유럽 거시 흐름을 문서형 근거로 보강 |
| 전처리 방식 | 수치 row를 브리핑 텍스트로 재구성, LLM 요약 가능 구조로 적재 |
| 저장 위치 | `external_document`, 로컬 다운로드 폴더 |
| 주요 사용 서비스 | `Market Regime`, 배치 실행 |

## 9. 파생 및 내부 관리 데이터

### 9.1 텍스트 구조화 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 뉴스/공시 구조화 결과 |
| 생성 주체 | `preprocessing.py`, Gemini |
| 데이터 설명 | 감성, 영향도, 이벤트 유형, 키워드 밀도, 개체 인식 결과 |
| 서비스 활용 용도 | 텍스트를 예측용 수치 feature로 변환 |
| 저장 위치 | `news_parsed.llm_payload`, `disclosure_parsed.llm_payload`, 분석 응답 JSON |
| 주요 사용 서비스 | `Stock Decision`, `Action Planner`, `Watchlist Alerts`, `Analyze Ticker` |

### 9.2 거시 표준 행 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 표준 거시 행 |
| 생성 주체 | `fetch_macro()`, `enrich_macro_rows()` |
| 데이터 설명 | 국가, 지표명, 실제값, 비교값, surprise, 방향 해석, 시간축 메타 |
| 서비스 활용 용도 | 거시 압력/지원 점수 계산, 시장 체제 설명 |
| 저장 위치 | `macro_snapshot` |
| 주요 사용 서비스 | `Market Regime`, `Stock Decision`, `Analyze Ticker` |

핵심 시간축 필드
- `observation_date`
- `release_at`
- `available_at`
- `ingested_at`
- `revision`
- `source_tz`
- `consensus_source`
- `surprise_raw`
- `surprise_index`
- `surprise_confidence`

### 9.3 특징값(feature) 세트

| 항목 | 내용 |
| --- | --- |
| 데이터명 | MarketFeatureSet |
| 생성 주체 | `feature_builder.py` |
| 데이터 설명 | 가격, 텍스트, 거시, 재무 데이터를 결합한 종합 feature 세트 |
| 서비스 활용 용도 | 신호 계산, 종목 판단, 행동 계획, 알림 여부 결정 |
| 저장 위치 | API 응답 내부, 알림 메시지 생성 입력 |
| 주요 사용 서비스 | 모든 사용자 제품 |

대표 묶음
- 가격 특징
- 뉴스/공시 특징
- 거시 특징
- 재무 특징

### 9.4 신호 및 품질 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 매매 신호, 품질 점수 |
| 생성 주체 | `signal.scorer`, `quality.gates` |
| 데이터 설명 | 방향, 점수, 품질 점수, 사유, 리스크 플래그 |
| 서비스 활용 용도 | 최종 판단과 알림 여부 결정 |
| 저장 위치 | `signal_decision`, API 응답 |
| 주요 사용 서비스 | `Stock Decision`, `Action Planner`, `Watchlist Alerts`, 텔레그램 알림 |

### 9.5 알림 관련 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 알림 이력 및 워치리스트 |
| 생성 주체 | `AnalysisPipeline`, `DecisionProductService` |
| 데이터 설명 | 발송 이력, 중복 방지용 fingerprint, 저장형 구독 정보 |
| 서비스 활용 용도 | 텔레그램 발송 관리, 중복 알림 방지, 관심종목 지속 관리 |
| 저장 위치 | `alert_history`, `watchlist_subscription` |
| 주요 사용 서비스 | `Watchlist Alerts` |

### 9.6 제품 스냅샷 데이터

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 제품 응답 스냅샷 |
| 생성 주체 | `DecisionProductService.refresh_market_regime_snapshot()` |
| 데이터 설명 | 시장 체제 결과를 미리 계산해 저장한 캐시 데이터 |
| 서비스 활용 용도 | 웹 첫 호출 속도 개선, 배치 선계산 |
| 저장 위치 | `product_snapshot_cache` |
| 주요 사용 서비스 | `Market Regime` |

### 9.7 로컬 원문 아카이브

| 항목 | 내용 |
| --- | --- |
| 데이터명 | 호출 단위 원문 아카이브 |
| 생성 주체 | `RawArchiveManager` |
| 데이터 설명 | 원문 본문, 메타데이터, raw PDF/DOCX/HTML/JSON 파일 |
| 서비스 활용 용도 | 근거 보존, 재현성 확보, 추후 재분석 |
| 저장 위치 | `downloads_dir` 하위 호출 폴더 |
| 주요 사용 서비스 | 전체 수집/배치/분석 파이프라인 |

기본 폴더 구조 예시

```text
downloads/
  analyze_ticker_YYYYMMDDTHHMMSSZ_<request_id>/
    snapshots/
    news/
    disclosures/
  batch_policy_YYYYMMDDTHHMMSSZ_<request_id>/
  batch_bok_YYYYMMDDTHHMMSSZ_<request_id>/
```

## 10. 서비스별 데이터 사용 매핑

### 10.1 Market Regime
- 가격 일봉
- 국내/미국/국제 거시 데이터
- 정책브리핑/한국은행/거시 브리핑 문서
- 공식 이벤트 일정
- 글로벌 이슈 스트림
- `product_snapshot_cache`

활용 목적
- 시장 체제를 `위험선호`, `중립`, `위험회피`로 구분
- 강세/약세 섹터 도출
- 전략 힌트 생성
- 문서형 거시 근거 제공

### 10.2 Stock Decision
- 종목 마스터
- 가격 일봉
- 뉴스
- 공시
- 재무제표
- 거시 데이터
- 정책/문서형 근거

활용 목적
- 최종 결론 `분할매수`, `보유`, `관찰`, `비중축소`
- 기간별 점수
- 상승/하락 요인
- 재무 요약
- 최근 이벤트 타임라인

### 10.3 Action Planner
- `Stock Decision` 산출물 전체
- 가격 현재값
- 변동성 및 품질 점수

활용 목적
- 매수 관심 구간
- 무효화 구간
- 목표 구간
- 보유자/미보유자 행동 계획
- 상방/중립/하방 시나리오

### 10.4 Watchlist Alerts
- 핵심 분석 결과
- 신호 점수
- 품질 점수
- 알림 이력
- 워치리스트 구독

활용 목적
- 즉시 점검 필요 여부
- 알림 미리보기
- 핵심 트리거와 리스크 플래그 제공

### 10.5 운영자 배치/문서 미리보기
- KIND 공시 문서
- 정책브리핑 문서
- 한국은행 문서
- 글로벌/국제 거시 브리핑 문서
- 공식 이벤트 일정
- 글로벌 이슈 스트림

활용 목적
- 원문 수집 상태 확인
- 정제 품질 확인
- DB 적재 품질 점검
- 시장 관련성 선별 결과 검토

## 11. 현재 카탈로그에 있으나 핵심 분석에 직접 연결되지 않은 항목

### 11.1 X API v2

| 항목 | 내용 |
| --- | --- |
| 상태 | 진단용 엔드포인트만 존재 |
| 원천 소스 | X API v2 |
| 현재 활용 여부 | 핵심 분석 파이프라인에는 직접 미반영 |
| 용도 | 외부 커넥터 연동 점검 또는 향후 소셜 시그널 확장용 |

정리
- `X_BEARER_TOKEN` 설정과 내부 진단 라우트는 존재한다.
- 하지만 현재 사용자 제품의 핵심 점수 계산에는 직접 사용하지 않는다.
- 따라서 이 문서에서는 “카탈로그 등록 및 진단 가능, 본 분석 미연계” 상태로 분류한다.

## 12. 소스 코드 기준 주요 구현 위치

| 역할 | 파일 |
| --- | --- |
| 원천 수집 | `app/services/ingestion/providers.py` |
| 문서형 배치 수집 | `app/services/ingestion/batch_ingestor.py` |
| 원문 로컬 저장 | `app/services/ingestion/raw_archive.py` |
| 텍스트/거시 전처리 | `app/services/ingestion/preprocessing.py` |
| 특징값 생성 | `app/services/features/feature_builder.py` |
| 종목 종합 분석 | `app/services/pipeline/orchestrator.py` |
| 사용자 제품 조립 | `app/services/intelligence/decision_products.py` |
| 시장 체제 계산 | `app/services/intelligence/market_pulse.py` |
| 소스 카탈로그 | `app/services/ingestion/source_catalog.py` |
| 저장 스키마 | `app/db/models.py` |

## 13. 운영 관점 확인 포인트

데이터를 점검할 때는 아래 순서로 보면 된다.

1. 원천 소스 호출 성공 여부 확인
2. 원문/원본 파일이 다운로드 폴더에 남았는지 확인
3. 전처리 후 구조화 필드가 생성됐는지 확인
4. DB 적재 위치가 맞는지 확인
5. 사용자 제품 응답에 근거 데이터가 실제 반영됐는지 확인

대표 점검 대상
- `instrument_master`: 종목 식별 정상 여부
- `price_daily`: 일봉 최신 적재 여부
- `news_parsed`, `disclosure_parsed`: 텍스트 구조화 여부
- `macro_snapshot`: 시간축 메타 포함 적재 여부
- `external_document`: 문서형 데이터 선별·요약 결과
- `release_calendar_event`: 공식 일정 적재 여부
- `product_snapshot_cache`: 시장 체제 배치 선계산 결과
- 다운로드 폴더: 원문 재현성 확보 여부

## 14. 문서 유지보수 원칙
- 새로운 데이터 소스를 추가하면 이 문서에 반드시 반영한다.
- “수집만 하고 쓰지 않는 데이터”와 “실제 제품에 반영되는 데이터”를 구분해 적는다.
- 원천 소스, 전처리 방식, 저장 위치, 활용 서비스 네 항목은 반드시 함께 기록한다.
- 문서 인코딩은 UTF-8, BOM 없음, 줄바꿈 LF를 유지한다.

## ?? ?? - ???? LLM ???? ?? peer ???
### ???? LLM ??? ???
- ?? ??: OpenDART, KIND ???? ?? ? ??
- ?? ??? ??: ????, ????, ????????, ????, ???, ?? ? ?? ??? ?? ??? ? ? ?? ?? ???
- ??? ?? ??: ?? ????? ?? ?? ? ??? ??, ?? ???, ?? ??? ???? ?? ??? ??
- ??? ??:
  - ?? ??? ??? LLM? ??? `bullish_score`, `bearish_score`, `net_score`, `event_severity`, `event_label`, `rationale` ??
  - LLM ?? ?? ???? ? ?? ?? fallback ??
  - ??? `enrich_disclosure_records()`?? `impact_score`, `sentiment_score`, `event_type`? ??
- ??/?? ??:
  - ?? ?? `explanation.material_disclosures`
  - feature: `disclosure_bullish_score`, `disclosure_bearish_score`, `disclosure_net_score`, `material_disclosure_severity`
  - signal/scorer?? ?? ???? ?? ??? ??

### ?? peer snapshot ???
- ?? ??: DART ?? ????, KIS ?? ??
- ?? ??? ??: ?? ??? ?? ??? ?? ???/peer ??? 20? ???, ?? ???, ???? Z-score
- ??? ?? ??: ??? ????? ?? ??? ?? ??? ?? ?? ??? ?? ?? ??
- ??? ??:
  - ?? ?? ???? ??
  - ??? ??? ????? ??
  - ?? peer ?? ???? ??? `peer_rows` ??
- ??/?? ??:
  - `SourceProviderClient.fetch_sector_momentum()` ??? `peer_rows`
  - `StockDecisionResponse.sector_peer_snapshot`
  - ? ???? ?? peer ?? ?

## 2026-03-14 추가 데이터 설명
### 수시공시 LLM 점수화
- 원천 소스: OpenDART, KIND 수시공시 제목/본문
- 활용 용도: 희석 리스크, 공급계약 호재, 주주환원 이벤트를 즉시 점수화해 종목 판단과 신호 계산에 반영
- 생성 필드: `disclosure_bullish_score`, `disclosure_bearish_score`, `disclosure_net_score`, `material_disclosure_severity`

### 섹터 peer snapshot
- 원천 소스: DART 종목 카탈로그, KIS 일봉 시세
- 활용 용도: 입력 종목이 섹터 내에서 어떤 위치에 있는지 사용자에게 설명하는 근거 표를 구성
- 생성 필드: `peer_rows`, `sector_peer_snapshot`

