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
