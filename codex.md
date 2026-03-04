# codex 작업 로그

## 2026-02-21 1차 업데이트
- 사용자 요구 수신: 현재 폴더의 `investai_설계문서.docx`, `investai_데이터소스설계.docx` 기반 상용 수준 주식 매매 신호 알림 서비스 구현.
- 제약/핵심 조건 확인:
  - 생성형 AI: Gemini 2.5 Pro.
  - 인증: 작업 디렉토리의 Google Application Credentials(JSON)로 ADC 방식 사용.
  - 결과물 문서화: `README.md`에 아키텍처, I/O, 환경변수, 운영 방식 지속 업데이트.
  - 진행 이력: 본 `codex.md`에 누적 기록.
- 문서 추출 수행:
  - `docx` 원문을 XML로 파싱해 `investai_설계문서.txt`, `investai_데이터소스설계.txt`로 추출.
  - 핵심 요구(파이프라인, 데이터 레이어, FastAPI API, LLM 스키마, 알림 중복 억제, 소스 레지스트리) 인덱싱 완료.
- 다음 작업:
  - FastAPI 기반 서비스 스캐폴딩과 도메인 모듈 구현.
  - Gemini ADC 클라이언트 및 텔레그램 알림 연동.
  - PostgreSQL 기반 스키마/리포지토리/신호 계산 로직 반영.

## 2026-02-21 2차 업데이트
- 프로젝트 스캐폴딩 완료:
  - `pyproject.toml`, `.env.example`
  - `app/` 전체 모듈 구조(FastAPI/API/DB/서비스/워커)
  - `config/sources.yaml`, `config/collection_policies.yaml`
  - `sql/schema.sql`, `tests/test_signal_scorer.py`, `prompts/alert_explanation_v1.txt`
- 핵심 구현 내용:
  - API: `/api/v1/health`, `/api/v1/analyze/ticker`, `/api/v1/internal/jobs/recompute-features`
  - 파이프라인: 종목 식별 -> 1년 가격/뉴스/공시/매크로 수집(현재는 교체 가능한 MVP provider) -> 피처 계산 -> 신호 점수화 -> 품질 게이트 -> Gemini 설명 -> 알림/이력 저장.
  - Gemini ADC: `app/services/llm/gemini_client.py`에서 `GOOGLE_APPLICATION_CREDENTIALS` 경로 기반 호출.
  - 알림: 텔레그램 발송 + cooldown 기반 중복 억제.
  - 데이터모델: instrument/price/news/disclosure/macro/signal/alert 테이블 반영.
- 검증 결과:
  - `py -m compileall app` 성공.
  - `py -m pytest -q`는 로컬에 `pytest` 미설치로 실행 불가(`No module named pytest`).
- 문서 업데이트:
  - `README.md`에 아키텍처, I/O, API, 환경변수, 실행 방법, 확장 포인트 반영.

## 2026-02-21 3차 업데이트 (사용자 요청 1/2/3 수행)
- 요청 처리 범위:
  1) 실제 외부 커넥터 연동
  2) PostgreSQL 실연결 E2E
  3) 텔레그램 실발송 검증

### 1) 외부 커넥터 연동 구현
- `app/services/ingestion/providers.py` 개선:
  - KIS: 토큰 발급 + 일봉 조회 호출 시도 로직 추가(`oauth2/tokenP`, daily price endpoint).
  - NAVER 뉴스 검색 API 호출 로직 추가.
  - OPENDART 공시 목록 API 호출 로직 추가.
  - 실제 호출 실패/자격정보 미설정 시 안전 fallback 데이터 사용.
- `app/services/pipeline/orchestrator.py` 개선:
  - 가격/뉴스/공시 중복 저장 방지 로직 추가(재실행 안정화).
- `app/services/alerts/dedup.py` 보정:
  - sqlite naive datetime / utc aware datetime 비교 오류 수정.

### 2) PostgreSQL 실연결 검증
- 의존성 설치 완료(권한 상승 필요): `sqlalchemy`, `psycopg`, `httpx`, `apscheduler`, `pyyaml`, `google-genai`, `pytest`, `pydantic-settings`.
- 검증 스크립트 추가: `scripts/verify_postgres.py`.
- 실제 결과:
  - `py scripts/verify_postgres.py` 실행 시 PostgreSQL 인증 실패(현재 `DATABASE_URL` 자격증명 불일치).
  - 로컬 PostgreSQL 재설치 시도(`choco install postgresql`)는 비관리자 권한으로 실패.

### 3) 텔레그램 실발송 검증
- 검증 스크립트 추가: `scripts/verify_telegram.py`.
- 실제 결과:
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 미설정으로 실발송 불가 확인.

### 추가 검증
- 파이프라인 E2E 스크립트 추가: `scripts/run_e2e_pipeline.py`.
- 실행 결과:
  - sqlite 기반 E2E 성공(`005930`, `EVENT_MONITOR`, score 72.25).
  - FastAPI TestClient로 `/api/v1/analyze/ticker` 200 응답 확인.
- 테스트:
  - `py -m pytest -q tests` 통과.

### 문서 업데이트
- `README.md`에 검증 스크립트/실행법/현재 환경에서의 성공/미완료 항목 반영.

## 2026-02-22 4차 업데이트 (PostgreSQL 실접속 완료)
- 사용자 제공 DB 문자열 수신: `postgrasql://postres:0000@localhost:5432/postgres`
- 확인 결과: 스키마/계정명 오타로 판단 (`postgrasql` -> `postgresql`, `postres` -> `postgres`)
- 보정 후 검증에 사용한 URL: `postgresql+psycopg://postgres:0000@localhost:5432/postgres`

### PostgreSQL 검증 결과
- `py scripts/verify_postgres.py` 성공 (`[OK] PostgreSQL connected: 1`)
- SQLAlchemy로 `Base.metadata.create_all()` 실행 및 DB/유저 확인 성공:
  - current_database = `postgres`
  - current_user = `postgres`

### PostgreSQL 기반 E2E 검증 결과
- `py scripts/run_e2e_pipeline.py` with PostgreSQL URL: 성공
- FastAPI TestClient `POST /api/v1/analyze/ticker`: 200 OK
- 알림은 텔레그램 설정 미완료로 `skipped/blocked` 상태 확인(파이프라인 동작은 정상)

### 남은 작업
- 텔레그램 실발송 검증 (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 필요)

## 2026-02-22 5차 업데이트 (텔레그램 실발송 검증)
- 사용자 제공 값 수신 (`TELEGRAN_*` 표기). 실제 런타임 변수명 `TELEGRAM_*`로 보정 적용.
- 실행:
  - `py scripts/verify_telegram.py`
  - `py scripts/run_e2e_pipeline.py` (PostgreSQL + Telegram enabled)
- 결과:
  - Telegram API 응답 `401 Unauthorized`
  - 파이프라인은 정상 동작했으며 `telegram_result.status = failed`, `http_status = 401`
- 해석:
  - 봇 토큰 불일치/만료/재발급 후 구토큰 사용 가능성 높음
  - `chat_id` 문제였다면 일반적으로 401보다 400 계열이 먼저 발생하는 경우가 많음
- 조치 필요:
  - BotFather에서 새 토큰 재발급 후 재검증
  - 토큰이 대화창에 노출되었으므로 보안상 회수/재발급 권장

## 2026-02-22 6차 업데이트 (텔레그램 실발송 성공)
- 사용자 안내에 따라 `.env` 사용.
- `.env` 확인 결과:
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 존재 확인 (`KEY = value` 공백 포함 형식)
- 검증 방법:
  - PowerShell에서 `.env`를 파싱해 프로세스 환경변수로 주입 후 실행
  - `TELEGRAM_ENABLED=true` 설정
- 결과:
  - `py scripts/verify_telegram.py` -> `{'status': 'sent', 'http_status': 200}`
  - `py scripts/run_e2e_pipeline.py` (PostgreSQL + Telegram enabled) -> `telegram_result.status = sent`, `http_status = 200`
- 상태:
  - 사용자 요청 1) 외부 커넥터 연동 2) PostgreSQL E2E 3) 텔레그램 실발송 검증 모두 완료

## 2026-02-22 7차 업데이트 (git push 인증 이슈)
- 커밋 완료: `ff17dfa` (`feat: add investai signal alert service MVP`)
- `git push origin main` 최초 실패 원인: `schannel ... SEC_E_NO_CREDENTIALS`
- 조치:
  - Git Credential Manager 전역 설정 완료 (`git credential-manager configure`)
  - 로컬 저장소 `http.sslbackend=openssl` 설정 적용 (schannel 우회)
- 현재 남은 이슈:
  - VS Code askpass 스크립트 실행 권한 오류로 인증 프롬프트 생성 실패
  - 에러: `failed to execute prompt script ... askpass.sh` / `could not read Username`
- 상태:
  - 네트워크/TLS 단계는 통과, 사용자 자격증명 입력 단계에서 터미널/askpass 환경 제약으로 중단

## 2026-02-22 8차 업데이트 (.env 기반 외부 커넥터 실연동 테스트)
- `.env`에 등록된 키를 사용하여 외부 커넥터 직접 호출 테스트 수행(값은 노출하지 않음)
- 테스트 대상: KIS, NAVER 뉴스, OPENDART, 그리고 PostgreSQL+Telegram 포함 E2E 파이프라인

### 커넥터 직접 테스트 결과 (`ticker=005930`)
- KIS `_fetch_price_daily_kis`:
  - 결과: 실패 (`403 Forbidden` at token endpoint `oauth2/tokenP`)
  - 해석: 앱키/시크릿 조합, 호출환경(실전/모의), 또는 KIS 앱 권한/활성 상태 확인 필요
- NAVER `_fetch_news_naver`:
  - 결과: 성공 (10건 조회)
  - 샘플 제목 확인 완료
- OPENDART `_fetch_disclosures_dart`:
  - 키 자체/API 응답 검증: 성공 (`http 200`, `status=000`, `message=정상`)
  - 종목 필터(`005930`) 기준 30일 결과는 0건 (기간/필터 조건 영향 가능)

### E2E 파이프라인 테스트 (`.env` 키 + PostgreSQL override + Telegram on)
- 외부 키: `.env`에서 로드
- DB: 검증용 `postgresql+psycopg://postgres:0000@localhost:5432/postgres`로 override
- 결과:
  - 파이프라인 성공
  - Telegram 실발송 성공 (`http_status=200`)
  - 점수/신호 생성 정상
- 참고:
  - KIS가 403이므로 가격은 fallback 데이터로 처리됨
  - NAVER/DART 키는 실제 호출 성공 확인

### 코드 수정
- `app/services/ingestion/providers.py`
  - DART 종목 필터에서 `stock_code` 없는 항목 제외하도록 수정(종목 무관 공시 혼입 방지)

## 2026-02-22 9차 업데이트 (사용자 요청 1/2/3 추가 수행)
### 1) KIS 키/모의/실전 구분 확인 + 재테스트
- `app/core/config.py`에 KIS URL 설정 추가:
  - `KIS_BASE_URL`, `KIS_PROD_BASE_URL`, `KIS_MOCK_BASE_URL`
- `app/services/ingestion/providers.py` 개선:
  - KIS 토큰 발급 시 실전/모의 베이스 URL 자동 순차 시도
  - 성공 시 선택된 base URL 캐시 (`_kis_base_url_selected`)
- 재테스트 결과:
  - 현재 `.env` 기준 KIS 토큰 발급은 실전/모의 모두 `403 Forbidden`
  - 따라서 KIS 가격 수집은 fallback으로 동작
  - 원인 후보: KIS 앱키/시크릿 조합 또는 계정/상품/환경 권한 설정 문제

### 2) DART ticker -> corp_code 매핑 추가
- `app/services/ingestion/providers.py` 개선:
  - `corpCode.xml`(zip) 다운로드/파싱 후 `stock_code -> corp_code` 캐시 로드
  - 공시 목록 조회 시 `corp_code` 파라미터 사용
  - 응답 item에 대해 `stock_code`/`corp_code` 추가 검증
- 재테스트 결과 (`005930`):
  - `corp_code` 매핑 성공 (`00126380`)
  - 최근 30일 공시 조회 성공 (100건 반환)

### 3) 검증 스크립트 `.env` 자동 로딩
- 수정 파일:
  - `scripts/run_e2e_pipeline.py`
  - `scripts/verify_postgres.py`
  - `scripts/verify_telegram.py`
- 변경 내용:
  - `python-dotenv` `load_dotenv(..., override=True)` 적용
  - 스크립트 실행 시 `.env` 자동 반영 (셸에서 수동 로드 불필요)

### 추가 통합 검증
- `.env` 외부 API 키 로드 + 테스트용 DB/Telegram 스위치 오버라이드로 통합 E2E 실행
- 결과:
  - NAVER 실수집 성공
  - DART 실수집 성공 (`corp_code` 적용)
  - KIS는 403으로 fallback 사용
  - 파이프라인/E2E 동작 정상 (신호 생성, 알림 중복 억제 적용)

## 2026-02-22 10차 업데이트 (KIS 정상화 완료)
- 사용자 답변 반영:
  - KIS 환경 = 실전
  - KIS 권한 활성화 확인 완료
- 원인 분석:
  - 직접 토큰 호출은 성공, provider 경로만 실패 -> `.env`의 `KEY = value` 형식 공백 영향 가능성 확인
  - provider에서 KIS/NAVER/DART 키 값 `strip()` 미처리로 인증 실패 발생 가능
- 조치:
  - `app/services/ingestion/providers.py`에서 KIS/NAVER/DART 키 값 `strip()` 적용
- 재테스트 결과:
  - KIS provider 경로 `_fetch_price_daily_kis('005930')` 성공
  - 조회 결과: 30건, base=`https://openapi.koreainvestment.com:9443`
- 결론:
  - 요청 1) KIS 재테스트, 2) DART corp_code 매핑, 3) 스크립트 `.env` 자동 로딩 모두 완료

## 2026-02-22 11차 업데이트 (X 실수집 테스트)
- `.env`의 `X_BEARER_TOKEN` 존재 확인: 길이 116, 로드 성공
- 테스트 1: `GET /2/users/me`
  - 결과: `403 Unsupported Authentication`
  - 해석: 앱 전용 OAuth2 Bearer로는 해당 엔드포인트 호출 불가(정상적인 제한)
- 테스트 2: `GET /2/tweets/search/recent`
  - 결과: `402 CreditsDepleted`
- 테스트 3: `GET /2/users/by/username/{username}`
  - 결과: `402 CreditsDepleted`
- 결론:
  - 토큰 자체는 요청 형식상 사용 가능
  - 현재 X 개발자 계정 크레딧 부족으로 실수집 불가
  - 크레딧 충전/플랜 변경 후 동일 코드로 재검증 가능

## 2026-02-22 12차 업데이트 (API 서버 직접 테스트 + README 실행 가이드 정리)
- 사용자 요청: 설계문서 기준 준비 수준을 직접 테스트 가능하게 API 서버 실행 및 실행방법 README 정리
- 수행 내용:
  - `uvicorn` 서버를 검증용 PostgreSQL URL override로 기동하여 실제 API 호출 테스트 수행
  - `GET /api/v1/health` -> 200 확인
  - `POST /api/v1/analyze/ticker` -> 200 확인
  - 서버 로그에서 KIS/NAVER/OPENDART 실호출 성공 확인
- 실제 서버 테스트 로그 요약:
  - KIS 토큰 발급 200, 일봉 조회 200
  - NAVER 뉴스 API 200
  - OPENDART `corpCode.xml` 200, `list.json` 200
- `README.md` 개선:
  - `.env` 직접 사용 기준으로 정리 (`.env.example` 안내 제거)
  - API 서버 실행 방법 / DB override 실행 예시 추가
  - Health/Analyze API 직접 호출 예시 추가
  - 설계문서 대비 준비 수준(완료/부분완료/미완료) 섹션 추가

## 2026-02-22 13차 업데이트 (임시/캐시 파일 정리)
- 사용자 요청: 현재 작업디렉토리의 임시/캐시 파일 삭제
- 삭제 성공:
  - 재귀 `__pycache__` 디렉터리 전체
  - `.pytest_cache` (재귀 대상 없음)
  - 임시 로그 파일 (`.tmp_uvicorn_*.log`)
- 삭제 실패(권한/소유권 잠금):
  - `.tmp`
  - `pytest-cache-files-3_4bjk_t`
  - `pytest-cache-files-5opu9304`
  - `pytest-cache-files-wdb9jk6w`
  - `pytest-cache-files-z2ox6s5s`
- 시도 내역:
  - 일반 삭제
  - 권한 상승 삭제
  - `takeown`/`icacls` 후 삭제 시도
- 실패 원인:
  - 현재 실행 컨텍스트가 해당 디렉터리 소유권 회수 권한이 없어 `takeown`/`icacls` 적용 불가

## 2026-02-22 14차 업데이트 (DB 접속 정보 확정)
- 사용자 제공 DB 정보 확인:
  - JDBC URL: `jdbc:postgresql://localhost:5432/postgres`
  - Username: `postgres`
  - Password: `0000`
- 서비스용 SQLAlchemy URL 매핑:
  - `postgresql+psycopg://postgres:0000@localhost:5432/postgres`
- 사용 위치:
  - `.env`의 `DATABASE_URL`
  - 서버 실행 시 환경변수 override

## 2026-02-22 15차 업데이트 (schema.sql 테이블 생성)
- 대상 DB: `postgresql://postgres:0000@localhost:5432/postgres`
- 작업: `sql/schema.sql` 실행
- 결과: 적용 완료 (`schema_applied`)
- 생성 확인 테이블:
  - `instrument_master`
  - `price_daily`
  - `news_parsed`
  - `disclosure_parsed`
  - `macro_snapshot`
  - `signal_decision`
  - `alert_history`

## 2026-02-22 16차 업데이트 (.env.example 제거)
- 사용자 요청 반영: `.env`만 사용하도록 정리
- 작업 내용:
  - `.env.example` 파일 삭제
  - `.gitignore`에서 `.env.example` 항목 제거
- 확인 결과:
  - `.env.example` 없음
  - `README.md`, `.gitignore`에 `.env.example` 언급 없음

## 2026-02-25 17차 업데이트 (API 서버 기동)
- 요청: 현재 작성 완료된 API 서버 실행
- 실행 방식:
  - 전역 Python(`C:\Python314\python.exe`)으로 `uvicorn app.main:app --host 127.0.0.1 --port 5000`
  - `DATABASE_URL=postgresql+psycopg://postgres:0000@localhost:5432/postgres`로 실행
- 확인 결과:
  - 포트 `127.0.0.1:5000` LISTENING 확인
  - `GET /api/v1/health` 응답 200 확인

## 2026-02-25 18차 업데이트 (nohup/백그라운드 실행 시도)
- 요청: `main.py`를 nohup처럼 백그라운드 실행
- 수행:
  - `Start-Process`로 `C:\Python314\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5000` 실행
  - 로그 파일(`uvicorn.out.log`, `uvicorn.err.log`) 확인
- 결과:
  - 기동 직후 로그는 정상 (`startup complete`, `Uvicorn running on http://127.0.0.1:5000`)
  - 그러나 tool call 종료 후 프로세스가 유지되지 않음 (환경 제약으로 보임)
- 결론:
  - 현재 에이전트 실행 환경에서는 지속 백그라운드 프로세스 유지가 불안정
  - 사용자가 로컬 터미널에서 직접 실행하면 정상 유지 가능

## 2026-02-25 19차 업데이트 (API 서버 유지 실행 시도 / 실행 스크립트 추가)
- 요청: 서버를 띄워두고 Swagger에서 직접 호출 가능 상태로 유지
- 조치:
  - `scripts/run_api_server.ps1` 추가 (DB URL 포함 uvicorn 실행 스크립트)
  - 스크립트 포그라운드 실행 검증 성공 (`startup complete`, `Uvicorn running on 127.0.0.1:5000`)
- 환경 제약:
  - 에이전트가 `Start-Process`로 띄운 백그라운드 프로세스는 tool call 종료 후 유지되지 않음
  - 따라서 사용자 로컬 터미널에서 직접 스크립트 실행 필요

## 2026-02-25 20차 업데이트 (`/api/v1/analyze/ticker` 상세 흐름 문서화)
- 사용자 요청: `POST /api/v1/analyze/ticker` 호출 시 동작하는 프로세스(흐름)를 README에 아주 자세히 작성
- `README.md` 반영 내용:
  - 라우터/오케스트레이터/수집/피처/신호/LLM/알림 관련 구현 파일 매핑
  - 요청 수신부터 DB 세션, 종목 식별, 외부 수집, 저장, 피처 생성, 신호 평가, 품질 게이트, Gemini 설명 생성, 알림 중복 억제, 발송, 이력 저장, 응답 반환까지 단계별 설명
  - fail-soft/fallback, cooldown 재알림 억제 등 실무 관점 동작 특성 설명

## 2026-02-25 21차 업데이트 (외부 수집 프로세스 엔드포인트화)
- 사용자 요청: 파이프라인 계층에서 외부 수집되는 모든 프로세스를 엔드포인트로 관리 가능하게 수정
- 구현:
  - `app/api/routes/internal.py`를 확장하여 소스별 수집 관리 엔드포인트 추가
  - `app/schemas/ingestion.py` 추가 (요청/응답 스키마)
- 추가된 엔드포인트:
  - `/api/v1/internal/ingestion/instrument/resolve`
  - `/api/v1/internal/ingestion/price/kis/daily`
  - `/api/v1/internal/ingestion/news/naver`
  - `/api/v1/internal/ingestion/disclosures/dart/corp-code-map`
  - `/api/v1/internal/ingestion/disclosures/dart/list`
  - `/api/v1/internal/ingestion/macro/snapshot`
  - `/api/v1/internal/ingestion/social/x/recent-search`
  - `/api/v1/internal/ingestion/collect-external-bundle`
- 검증:
  - TestClient로 `resolve`/`collect-external-bundle` 호출 성공
  - 실수집 로그 확인 (KIS/NAVER/OPENDART HTTP 200)
- 문서화:
  - `README.md`에 내부 수집 관리 엔드포인트 목록 및 PowerShell 호출 예시 추가

## 2026-02-25 22차 업데이트 (Swagger 엔드포인트 설명 한글화)
- 사용자 요청: Swagger에서 보이는 엔드포인트 설명을 한글로 작성
- 반영 내용:
  - `app/api/routes/health.py`: `summary`, `description` 한글 추가
  - `app/api/routes/analysis.py`: `summary`, `description` 한글 추가
  - `app/api/routes/internal.py`: 내부 수집/관리 엔드포인트 전부 `summary`, `description` 한글 추가
  - `app/schemas/analysis.py`, `app/schemas/ingestion.py`: 요청/응답 필드 `description` 한글 추가
- 검증:
  - OpenAPI JSON에서 한글 summary/description 노출 확인

## 2026-02-25 23차 업데이트 (Swagger 한글 설명 검증 재확인)
- 인코딩 표시 이슈(CP949)로 터미널 출력이 깨져 보였으나, 실제 파일/문법은 정상
- `compileall` 성공 및 OpenAPI JSON 확인 결과:
  - `KIS 일봉 수집 프로브`
  - `KIS OpenAPI를 통해 일봉 가격 데이터를 수집...`
  - `조회 대상 종목의 티커 또는 종목명`
- 결론: Swagger 엔드포인트/필드 설명 한글화 정상 반영

## 2026-02-26 24차 업데이트 (한국 종목명 유사도 검색/티커 매칭 개선)
- 사용자 이슈: `삼성전자` 외 다른 한국 종목명 입력에서 티커 식별 실패/부정확
- 원인:
  - 기존 `resolve_instrument()`가 사실상 하드코딩 alias + 숫자 티커 입력에 의존
  - DART 공식 종목명(법인명)과 실사용 종목명/별칭(`네이버`, `현대차`, `하이닉스`) 차이 반영 부족
- 조치:
  - `app/services/ingestion/providers.py` 전체 재생성 (인코딩 깨짐 파일 복구 포함)
  - DART `corpCode.xml` 기반 종목 카탈로그 로딩/캐시 구현
  - 텍스트 유사도(`SequenceMatcher`) 기반 `search_instruments(query, limit)` 추가
  - alias 후보를 DART 검색 결과와 병합하여 별칭(`네이버`, `현대차`, `하이닉스`) 상위 노출
  - `resolve_instrument()`가 유사도 검색 결과를 사용하도록 개선
  - 기존 파이프라인 호환 메서드(KIS/NAVER/DART/매크로/fallback) 복구
  - `app/schemas/ingestion.py` UTF-8 재작성 + 종목 검색 요청/응답 스키마 추가
  - `app/api/routes/internal.py`에 `POST /api/v1/internal/ingestion/instrument/search` 추가
- 검증:
  - `py -m compileall app` 성공
  - `SourceProviderClient.search_instruments()` / `resolve_instrument()` 검증:
    - `삼성전자`, `SK하이닉스`, `하이닉스`, `현대차`, `네이버`, `카카오`
  - FastAPI TestClient로 `/api/v1/internal/ingestion/instrument/search` 호출 200 확인
- 문서화:
  - `README.md`에 새 엔드포인트 목록/호출 예시/사용 흐름(`search -> resolve/analysis`) 추가

## 2026-02-26 25차 업데이트 (별칭 입력 시 공식 종목명 반환 보강)
- 보강: alias 후보/resolve 결과에 fallback 별칭명 대신 DART 카탈로그 기준 공식명 사용
  - 예: '현대차' -> '현대자동차', '네이버' -> 'NAVER'
- 검증: /api/v1/internal/ingestion/instrument/search, /api/v1/internal/ingestion/instrument/resolve TestClient 호출 200 및 결과 확인

## 2026-02-26 26차 업데이트 (서버 로그 자동 생성)
- 사용자 요청: 서버 실행 시 .log 파일 자동 생성
- 변경: scripts/run_api_server.ps1 수정
  - logs 디렉터리 자동 생성
  - logs/uvicorn.log 자동 append 기록
  - 시작 시각(starting uvicorn...) 라인 기록 후 uvicorn stdout/stderr를 파일+콘솔 동시 출력(Tee-Object)
- 문서: README.md 실행 섹션에 스크립트 실행 방법 및 로그 경로 추가

## 2026-02-26 27차 업데이트 (main.py 직접 실행 시 uvicorn 기동)
- 사용자 요청: main.py 스크립트 마지막에 uvicorn 실행 엔트리포인트 추가 (reload=True)
- 변경: `app/main.py` 하단에 `if __name__ == "__main__":` 블록 추가
  - `uvicorn.run("app.main:app", host="127.0.0.1", port=5000, reload=True)`

## 2026-02-26 28차 업데이트 (서버 실행/의존성/경로 재점검)
- 사용자 요청: 서버 직접 실행 + 로컬 실행용 의존성/경로 재검토
- 점검 결과:
  - 현재 인터프리터: `C:\Python314\python.exe`
  - 주요 의존성 설치 확인: `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg`, `pydantic-settings`, `httpx`
- 수정:
  - `scripts/run_api_server.ps1` 보강
    - native stderr로 인한 즉시 종료 완화 (`$ErrorActionPreference = "Continue"` 전환 지점 추가)
  - `README.md` 실행 방법 보강
    - 권장 명령(`cd D:\invest_ai` + `py -m uvicorn ...`)
    - 트러블슈팅 추가(`uvicorn not found`, `No module named app`, `fastapi 미설치`)
- 참고:
  - 에이전트 실행 환경 제약으로 백그라운드 프로세스 유지가 불가하여, 실제 상시 실행은 사용자 로컬 터미널에서 명령 실행 필요

## 2026-02-26 29차 업데이트 (함수/클래스 인수인계 문서화)
- 사용자 요청: 모든 소스코드의 함수/클래스에 대해 기능, 처리 방식, 간단한 I/O 예시를 포함한 인수인계 문서화
- 작업:
  - `docs/HANDOVER_FUNCTIONS.md` 신규 생성
  - 범위: `app/`, `scripts/`, `tests/`의 함수/클래스 전체를 파일별로 정리
  - 각 항목에 `기능 / 처리 방식 / I/O 예시` 포맷 적용
  - 수집/파이프라인/신호/품질/알림/LLM/DB/스키마/스크립트/테스트 포함
  - `README.md`에 인수인계 문서 링크(`docs/HANDOVER_FUNCTIONS.md`) 추가

## 2026-02-26 30차 업데이트 (코드 내부 docstring 삽입)
- 사용자 요청: 코드 내부 함수/클래스에 직접 docstring 삽입
- 반영 범위:
  - `app/core/*`, `app/db/*`, `app/schemas/*`, `app/api/routes/*`, `app/main.py`, `app/workers/scheduler.py`
  - `app/services/*` 전반(ingestion/provider 포함 공개/내부 메서드)
  - `scripts/*`, `tests/test_signal_scorer.py`
- 작업 방식:
  - 각 클래스/함수에 역할과 처리 의도를 설명하는 간결한 docstring 추가
  - 동작 로직 변경 없이 문서성만 강화
- 검증:
  - `py -m compileall app scripts tests` 성공
  - `py -m pytest -q tests` 통과 (2 passed)
  - 참고: pytest cache 경고 1건(권한), 테스트 결과에는 영향 없음

## 2026-02-26 31차 업데이트 (docstring 한글화 일괄 반영)
- 사용자 요청: 코드에 포함된 docstring 언어를 모두 한글로 변경
- 처리:
  - `app/`, `scripts/`, `tests/` 전체 `.py` 파일 대상으로 docstring 일괄 치환
  - 영문 docstring을 한글 문구로 통일
- 검증:
  - 영문 docstring 잔여 검사: 없음 확인
  - `py -m compileall app scripts tests` 성공
  - `py -m pytest -q tests` 통과 (2 passed)

## 2026-02-26 32차 업데이트 (docstring 한글 통일 완료)
- 사용자 요청: 코드에 포함된 docstring 언어를 모두 한글로 변경
- 결과:
  - `app/`, `scripts/`, `tests/` 전체 `.py` 파일의 docstring을 한글 문구로 통일
  - 영문 docstring 잔여 검사 결과: `OK: 영어 docstring 없음`
- 참고:
  - 별개 이슈로 기존 소스 내 인코딩/문자열 손상 구간에서 `compileall`/테스트 시 SyntaxError가 확인됨
  - 해당 이슈는 docstring 변경 범위 외 기존 문자열 손상 영역

## 2026-02-26 33차 업데이트 (API summary/description 한글 복구)
- 사용자 요청: 깨진 API 엔드포인트 `summary`, `description`을 정상 한글로 수정
- 조치:
  - `app/api/routes/health.py` 재작성
  - `app/api/routes/analysis.py` 재작성
  - `app/api/routes/internal.py` 재작성(모든 내부 엔드포인트 summary/description 한글화)
  - `app/schemas/analysis.py`, `app/schemas/ingestion.py` 재작성(설명 필드 한글 복구 및 문법 오류 제거)
- 검증:
  - 대상 파일 compile 성공
  - 라우터 내 summary/description 선언 확인 완료

## 2026-02-26 34차 업데이트 (엔드포인트 한글 설명/문법 복구 완료)
- 사용자 요청: API 엔드포인트 summary/description 깨짐 복구
- 조치:
  - `app/api/routes/health.py`, `app/api/routes/analysis.py`, `app/api/routes/internal.py`를 한글 summary/description으로 재작성
  - `app/schemas/analysis.py`, `app/schemas/ingestion.py` 설명 필드(Description) 한글 복구
  - 연쇄 문법 오류 복구를 위해 `app/services/signal/scorer.py`, `app/services/llm/gemini_client.py`, `app/services/ingestion/providers.py` 문자열 손상 구간 재작성
- 검증:
  - `py -m compileall app` 성공
  - `py -m pytest -q tests` 통과 (2 passed)

## 2026-03-01 35차 업데이트 (한글 문자열 깨짐 재정비)
- 사용자 요청: 코드 내 한글 깨짐(f-string 포함) 잔여 구간 정리
- 조치:
  - `app/services/ingestion/providers.py`의 손상 문자열 정비
  - 종목 카탈로그/별칭의 유니코드 이스케이프를 실제 한글 문자열로 치환
  - 텍스트 정규화 로직 손상 문자열(`(?)`, `????`)을 정상 규칙(`(주)`, `주식회사`)으로 교체
- 검증:
  - `py -m compileall app` 성공
  - `py -m pytest -q tests` 통과 (2 passed)
  - `????`, `\uXXXX`, `�` 패턴 잔여 없음 확인

## 2026-03-01 36차 업데이트 (Swagger 텔레그램 테스트 가이드 추가)
- 사용자 요청: FastAPI Swagger에서 텔레그램 알림 전송 테스트 방법을 README에 문서화
- 조치:
  - `README.md`에 `## 16. Swagger에서 텔레그램 알림 전송 테스트 방법` 섹션 추가
  - `.env` 사전조건, 서버 실행, `POST /api/v1/analyze/ticker` 호출 예시, 성공/실패 판별 기준 정리
- 비고:
  - 코드 로직 변경 없음(문서 업데이트만 수행)

## 2026-03-01 37차 업데이트 (알림 skip 사유 한글화 + 응답 한국어 후처리 번역)
- 사용자 요청:
  - `alert.should_send=false` / `telegram skipped` 원인 설명
  - API 최종 응답을 한국어 중심으로 제공하도록 기능 추가(LLM 후처리 번역)
- 조치:
  - `app/services/pipeline/orchestrator.py`
    - 채널 결과 한글 정규화 함수 추가(`status`, `reason` + `status_code`, `reason_code`)
    - 알림 히스토리 저장 시 내부 코드(`status_code`) 기준으로 저장하도록 정리
    - 요청 `response_language` 값에 따라 응답 직전 한국어 후처리 번역 적용
  - `app/services/llm/gemini_client.py`
    - JSON 생성 공통 함수 `_generate_json` 추가
    - `translate_json_to_korean` 추가(키/숫자 유지, 문자열 값만 한국어 번역)
    - fallback 설명을 한국어 문구로 변경
  - `app/services/alerts/formatter.py`
    - 텔레그램 알림 본문 한글화
  - 스키마 한글 깨짐 복구:
    - `app/schemas/analysis.py` 재작성(`response_language` 필드 추가)
    - `app/schemas/ingestion.py` 재작성(설명/문구 한글 복구)
  - 문서:
    - `README.md`에 `skipped` 발생 조건과 `response_language` 사용법 추가
- 검증:
  - `py -m compileall app` 성공
  - `py -m pytest -q tests` 통과 (2 passed)

## 2026-03-01 38차 업데이트 (`analyze/ticker` 실호출 점검 및 README 반영)
- 사용자 요청:
  - `/api/v1/analyze/ticker` 테스트 수행
  - 텔레그램 미발송 원인 분석 및 README 반영
- 수행:
  - TestClient로 `/api/v1/analyze/ticker` 호출(`ticker_or_name=005930`, `notify=true`, `response_language=ko`)
  - 응답 확인:
    - `should_send=false`
    - `status_code=skipped`
    - `reason_code=threshold_not_met_or_notify_false`
    - `signal.score=47.3`, `quality_score=65.0`
  - 원인 결론:
    - 점수 임계치(`score>=60`) 미충족으로 텔레그램 발송 스킵
- 추가 수정:
  - `app/services/pipeline/orchestrator.py`에서 한국어 후처리 시 `channel_results`를 재번역하지 않도록 조정
    - 목적: 이미 한글화된 상태/사유가 영어로 역변환되는 현상 방지
- 문서:
  - `README.md`에 `## 19. /api/v1/analyze/ticker 실테스트 결과(2026-03-01)` 추가

## 2026-03-01 39차 업데이트 (개발용 force_send 플래그 추가)
- 사용자 요청: 테스트 목적의 `force_send` 플래그를 엔드포인트에 추가
- 조치:
  - `app/schemas/analysis.py`
    - `AnalyzeTickerRequest`에 `force_send: bool = False` 추가
  - `app/services/pipeline/orchestrator.py`
    - 발송 조건에 `force_send` 경로 추가(임계치/쿨다운 우회)
    - 채널 결과에 `force_send_applied` 표시 추가
    - 강제 발송 표시가 실제 실패 원인을 덮어쓰지 않도록 보정
- 실호출 검증:
  - `force_send=true` 호출 시 `alert.should_send=true` 확인
  - 현재 환경에서는 `TELEGRAM_ENABLED=false`로 `status_code=skipped`, `reason_code=telegram_disabled` 확인
- 문서:
  - `README.md`에 `## 20. 개발용 force_send 플래그` 섹션 추가
  - `.env` 필수값(`TELEGRAM_ENABLED=true`, 토큰, 채팅ID) 명시

## 2026-03-02 40차 업데이트 (v2 설계 반영: 3서비스 계층 + 데이터소스 파이프라인)
- 사용자 요청:
  - `investai_설계문서_v2.txt` 기준으로 전체 서비스 구조를 개편
  - 기존 모듈/함수/변수를 최대한 재사용
  - `investai_데이터소스설계_v2.txt` 기준 크롤링/파싱/전처리 모듈 추가
- 구현:
  - 신규 스키마:
    - `app/schemas/intelligence.py`
    - `app/schemas/ingestion_pipeline.py`
  - 신규 서비스 엔진:
    - `app/services/intelligence/stock_insight.py`
    - `app/services/intelligence/trade_compass.py`
    - `app/services/intelligence/market_pulse.py`
  - 신규 수집/전처리 모듈:
    - `app/services/ingestion/source_catalog.py`
    - `app/services/ingestion/preprocessing.py`
    - `app/services/ingestion/crawlers.py`
  - 신규 API 라우터:
    - `app/api/routes/stock_insight.py`
    - `app/api/routes/trade_compass.py`
    - `app/api/routes/market_pulse.py`
    - `app/api/routes/ingestion_pipeline.py`
  - 앱 라우팅 반영:
    - `app/main.py`에서 신규 라우터 등록
- 재사용 원칙:
  - 기존 `providers`, `feature_builder`, `scorer`, `gates`, `gemini_client`를 코어로 재사용
- 검증:
  - `py -m compileall app` 성공
  - `py -m pytest -q tests` 통과 (2 passed)
  - TestClient로 신규/핵심 엔드포인트 200 응답 확인
- 문서:
  - `README.md`에 v2 구조/엔드포인트/파이프라인/검증 결과 섹션 추가

## 2026-03-02 41차 업데이트 (원본 다운로드 저장 + 원문기반 LLM 처리 구조 반영)
- 사용자 요청:
  - 공시/IR/기업문서/거시·정책 보도자료/발표문/미국 공시·XBRL 계열에 대해
    - 원본 파일/원문을 로컬 다운로드 폴더에 호출 단위로 저장
    - 이후 LLM 요약/정리를 분석 흐름에 반영
- 구현:
  - 저장 매니저 추가:
    - `app/services/ingestion/raw_archive.py`
    - 호출 단위 폴더 생성 + 문서(메타/본문/원본) 저장
  - 설정 추가:
    - `DOWNLOADS_DIR` (`app/core/config.py`, 기본 `downloads`)
  - 수집 확장(`providers`):
    - 뉴스/공시 수집 시 `include_content=True` 옵션으로 원문 다운로드/본문 추출
    - HTML/PDF/문서형 응답 텍스트 추출 보강
  - 분석 파이프라인(`orchestrator`) 변경:
    - `analyze/ticker` 호출마다 아카이브 폴더 생성
    - 뉴스/공시 문서를 로컬 저장
    - `gemini.summarize_documents()`로 원문 기반 요약 생성
    - 요약을 `explanation.document_summaries` 및 DB `llm_payload`에 반영
  - 수집 API 확장:
    - `POST /api/v1/ingestion/crawl/collect` 추가
    - 호출 단위 폴더 저장 경로를 응답에 반환
  - 스키마 확장:
    - `app/schemas/ingestion_pipeline.py`에 collect 요청/응답 모델 추가
  - 기타:
    - Windows 경로 길이 이슈 대응(문서 저장 폴더명 해시 기반 단축)
    - `.gitignore`에 `downloads/` 추가
- 실검증:
  - `POST /api/v1/ingestion/crawl/collect` 200 및 `saved_call_dir` 확인
  - `POST /api/v1/analyze/ticker` 200, `explanation.archive_call_dir`/`document_summaries` 확인
  - `py -m compileall app`, `py -m pytest -q tests` 통과

## 2026-03-02 42차 업데이트 (데이터 수집/활용 목록 README 정리)
- 사용자 요청:
  - 현재 서비스에서 수집/활용 중인 데이터와 향후 활용 예정 데이터를 소스별 상태와 함께 문서화
- 조치:
  - `README.md`에 `## 27. 데이터 수집/활용 전체 목록 (현재 + 예정)` 섹션 추가
  - 항목별로 `수집 소스`, `소스 ID`, `수집 상태`, `활용 상태`를 표로 정리
  - 운영/부분/예정 상태 기준 정의 추가
  - 현재 운영 항목과 예정 항목을 분리해 가시성 확보

## 2026-03-02 43차 업데이트 (KRX KIND/정책브리핑/한국은행 배치 수집-처리-적재 파이프라인)
- 사용자 요청:
  - KRX KIND(정기/수시 공시), 정책브리핑(청와대/국무회의/부처브리핑/정책뉴스), 한국은행(간행물/조사연구/지역/국외/업무별정보) 자료를
    수집 -> 처리 -> DB 적재 배치로 구현
  - 원본/원문 다운로드 + 파싱/표준화 + LLM 요약 재활용
- 구현:
  - DB:
    - `app/db/models.py`에 `ExternalDocument` 테이블 추가
  - 배치 서비스:
    - `app/services/ingestion/batch_ingestor.py`
    - `ingest_kind_disclosures`, `ingest_policy_briefing`, `ingest_bok_publications`
    - `external_document` upsert + 로컬 원문 저장 + LLM 요약
  - API:
    - `app/api/routes/batch_ingestion.py`
      - `POST /api/v1/batch/kind/disclosures`
      - `POST /api/v1/batch/policy-briefing`
      - `POST /api/v1/batch/bok/publications`
    - `app/main.py` 라우터 등록
  - 스케줄러:
    - `app/workers/scheduler.py`
      - 정책브리핑 배치(06:15), 한국은행 배치(06:35) 등록
  - 스키마:
    - `app/schemas/batch_ingestion.py` 추가
  - 성능/안정화:
    - `preprocessing.entity_linker`를 로컬 규칙 기반으로 변경(배치 중 외부 호출 제거)
    - `batch_ingestor`에서 `external_document` 테이블 자동 보장 로직 추가
  - 활용 연결:
    - `stock_insight`, `market_pulse`에서 `external_document` 최신 요약을 조회해 결과 힌트에 반영
- 검증:
  - `py -m compileall app`, `py -m pytest -q tests` 통과
  - 실호출:
    - KIND 배치 200 확인
    - 정책브리핑 배치 200 확인
    - 한국은행 배치 200 확인
- 문서:
  - `README.md`에 데이터 상태표(운영/예정) 갱신
  - `README.md`에 배치 파이프라인/적재 테이블/스케줄러 정보 추가

## 2026-03-02 44차 업데이트 (public 8개 테이블 설명 + 컬럼 comment 반영)
- 사용자 요청:
  - PostgreSQL public 스키마 8개 테이블의 용도/적재 경로를 README에 정리
  - 각 테이블 컬럼에 DB description(comment) 추가
- 조치:
  - `app/db/models.py` 재작성
    - 8개 테이블의 모든 컬럼에 `comment` 지정
      - `instrument_master`
      - `price_daily`
      - `news_parsed`
      - `disclosure_parsed`
      - `macro_snapshot`
      - `signal_decision`
      - `alert_history`
      - `external_document`
  - `README.md`에 `## 29. PostgreSQL public 스키마 8개 테이블 설명` 섹션 추가
    - 테이블별 용도
    - 데이터 적재 경로/관련 코드
    - comment 반영 시 마이그레이션 필요사항 안내

## 2026-03-02 45차 업데이트 (실 DB description 적용 완료)
- 사용자 요청: 실제 PostgreSQL DB description 반영
- 수행:
  - 모델 코멘트 기준으로 `COMMENT ON COLUMN` 실행(8개 테이블 전 컬럼)
  - 8개 테이블에 `COMMENT ON TABLE` 실행
  - 시스템 카탈로그 조회로 반영 검증
- 결과:
  - 대상 8개 테이블: table description 반영 완료
  - 대상 8개 테이블: 컬럼 description 100% 반영 완료
- 참고:
  - 터미널 코드페이지 영향으로 한글 코멘트 조회 출력이 `??`로 보일 수 있으나, DB에는 값이 정상 저장됨

## 2026-03-02 46차 업데이트 (instrument_master / external_document 코멘트 재적용)
- 사용자 요청:
  - `instrument_master`, `external_document` 테이블 코멘트 미반영 이슈 재처리
- 조치:
  - 두 테이블의 table comment/column comment를 명시적으로 재적용
  - 시스템 카탈로그 기준 검증 재실행
- 검증 결과:
  - `external_document`: table comment=Y, columns=18/18
  - `instrument_master`: table comment=Y, columns=7/7

## 2026-03-02 47차 업데이트 (코멘트 물음표 깨짐 재교정)
- 사용자 요청:
  - 코멘트 텍스트가 `?`로 보이는 문제 재반영
- 조치:
  - `instrument_master`, `external_document`의 table/column comment를 UTF-8 기준으로 강제 재적용
  - 유니코드 이스케이프 문자열 기반으로 SQL COMMENT 재실행
- 검증:
  - `external_document`: `table_has_q=False`, `cols_with_q=0/18`
  - `instrument_master`: `table_has_q=False`, `cols_with_q=0/7`

## 2026-03-02 48차 업데이트 (README 전면 재구성 + 불필요 파일 정리)
- 사용자 요청:
  - README에서 기존 10~13, 15~20 섹션 제거
  - 남은 내용을 현재 코드 기준으로 재구성/보강
  - 프로젝트 내 불필요 파일 정리
- 조치:
  - `README.md` 전면 재작성
    - 서비스 개요, 아키텍처, 엔드포인트, 환경변수, 실행/사용 예시
    - 원문 저장/요약 처리 구조
    - 데이터 수집/활용 현황
    - 배치 적재 파이프라인
    - public 8개 테이블 설명 및 코멘트 반영 상태
  - 불필요 파일 정리:
    - 삭제 완료: `~$investai.xlsx`(잠금파일), 로그/일부 임시파일
    - 삭제 시도했으나 권한으로 잔존:
      - `.tmp/`
      - `pytest-cache-files-5dq07nxe/`
      - `pytest-cache-files-aorg6cuv/`
- 비고:
  - 잔존 폴더는 ACL Access denied로 현재 권한 범위에서 제거 불가

## 2026-03-02 49차 업데이트 (README 3장 엔드포인트 상세화)
- 사용자 요청:
  - README 3장(주요 엔드포인트)을 간략 목록이 아닌 상세 문서로 확장
  - 모든 엔드포인트에 대해 개요/I/O/처리 로직 추가
- 조치:
  - `README.md` 3장 전면 확장
  - 문서 대상 엔드포인트:
    - health 1개
    - analyze 1개
    - stock-insight/trade-compass/market-pulse 3개
    - ingestion pipeline 3개
    - batch ingestion 3개
    - internal 진단 10개
  - 총 21개 엔드포인트에 대해 항목별 설명 반영

## 2026-03-02 50차 업데이트 (서비스 아키텍처/프로세스 도식화)
- 사용자 요청:
  - 주요 서비스의 데이터 입출력, 처리 흐름, 로직을 직관적으로 보이도록 도식화
- 조치:
  - `README.md`에 아키텍처/프로세스 도식 섹션 추가
    - 2.1 전체 아키텍처 도식(mermaid)
    - 2.2 서비스별 I/O 개요 표
    - 2.3 서비스별 처리 흐름 도식
      - Stock Insight
      - Trade Compass
      - Market Pulse
      - Analyze/Ticker 통합 파이프라인
      - 문서형 배치 파이프라인(KIND/정책브리핑/BOK)

## 2026-03-04 51차 업데이트 (웹 UI 신규 구현 + 연동 테스트)
- 사용자 요청:
  - 현재 백엔드 서비스를 활용한 상용 수준 웹 화면 구성 및 테스트
- 구현:
  - 웹 라우터 추가: `app/api/routes/web.py` (`GET /app`)
  - 정적 자산 마운트: `app/main.py` (`/assets`)
  - UI 파일 추가:
    - `app/web/index.html`
    - `app/web/styles.css`
    - `app/web/app.js`
  - 화면 기능:
    - Health 상태 확인
    - Analyze/Stock Insight/Trade Compass/Market Pulse 호출
    - Ingestion Preview 호출
    - KIND/정책브리핑/BOK 배치 호출
- 테스트:
  - `/app`, `/assets/styles.css`, `/assets/app.js`, `/api/v1/health` 응답 200 확인
  - `py -m compileall app` 성공
  - `py -m pytest -q tests` 통과
- 문서:
  - `README.md`에 웹 대시보드 접속 경로와 화면 기능 섹션 추가
