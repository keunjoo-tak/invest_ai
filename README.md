# InvestAI Signal Alert Service

`investai_설계문서.docx`, `investai_데이터소스설계.docx` 요구사항을 반영한 반자동 주식 매매 신호 알림 서비스입니다.

## 1. 서비스 개요
- 목적: 종목 입력 시 최근 1년 데이터 기반으로 신호 후보를 생성하고, 근거/리스크 설명과 함께 알림 전송.
- 범위: 자동 주문 없음(사용자 수동 주문), 알림 중심.
- 대상 시장: KR(초기), US 확장 가능 구조.
- LLM: Gemini 2.5 Pro (ADC: Application Default Credentials).

## 2. 아키텍처
- API 계층: FastAPI (`app/main.py`, `app/api/routes/*`)
- 파이프라인 계층: 수집 -> 피처 -> 신호 -> 품질게이트 -> LLM 설명 -> 알림 (`app/services/pipeline/orchestrator.py`)
- 데이터 계층: PostgreSQL + SQLAlchemy (`app/db/*`, `sql/schema.sql`)
- 운영 계층: 스케줄러 골격(향후 큐 워커 확장) (`app/workers/scheduler.py`)
- 설정 계층: `.env` + 소스/정책 YAML (`config/sources.yaml`, `config/collection_policies.yaml`)

## 3. 데이터 레이어(I/O 관점)
- 입력:
  - API 입력: `ticker_or_name`, `as_of_date`, `lookback_days`, `notify`, `channels`
  - 외부 소스(추상화): KIS, OPENDART, KIND, NAVER_SEARCH, X API
  - LLM 입력: 신호/피처/근거 JSON
- 처리:
  - Raw/Parsed/Feature/Signal 단계 분리 설계
  - 중복 알림 억제(fingerprint + cooldown)
  - 품질 게이트(quality score, 유동성, 가격 유효성)
- 출력:
  - API 응답: 신호 점수, 근거코드, 리스크, 설명, 알림 발송결과
  - DB 저장: `signal_decision`, `alert_history` 등
  - 알림 채널: 텔레그램(우선 구현)

## 4. API 명세(MVP)
- `GET /api/v1/health`
  - 상태 확인
- `POST /api/v1/analyze/ticker`
  - 종목 분석 + 신호 생성 + 알림 후보 생성/발송
- `POST /api/v1/internal/jobs/recompute-features`
  - 내부 작업 트리거 샘플 엔드포인트

요청 예시:

```json
{
  "ticker_or_name": "005930",
  "lookback_days": 365,
  "analysis_mode": "full",
  "notify": true,
  "channels": ["telegram"]
}
```

## 5. 환경변수
핵심 환경변수는 `.env.example` 참고.

- 앱/DB:
  - `APP_NAME`, `APP_ENV`, `API_PREFIX`, `TIMEZONE`
  - `DATABASE_URL`
- Gemini(ADC):
  - `GOOGLE_APPLICATION_CREDENTIALS` (현재 작업폴더 credential JSON 경로)
  - `GEMINI_PROJECT_ID`, `GEMINI_LOCATION`, `GEMINI_MODEL`, `GEMINI_ENABLED`
- 알림:
  - `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALERT_COOLDOWN_MINUTES`
- 수집 소스:
  - `KIS_APP_KEY`, `KIS_APP_SECRET`, `DART_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `X_BEARER_TOKEN`

## 6. Gemini 2.5 Pro (ADC) 호출 방식
- 구현 파일: `app/services/llm/gemini_client.py`
- 동작:
  - `GOOGLE_APPLICATION_CREDENTIALS`를 사용해 ADC 인증
  - Vertex AI 경유 `gemini-2.5-pro` 호출
  - JSON 응답 강제(`response_mime_type=application/json`)
  - 실패 시 안전한 fallback 설명 생성

## 7. 실행 방법
1. 의존성 설치
```bash
py -m pip install --user fastapi uvicorn sqlalchemy psycopg[binary] httpx apscheduler pyyaml google-genai pydantic-settings pytest
```
2. 환경변수 파일 준비
```bash
copy .env.example .env
```
3. 서버 실행
```bash
uvicorn app.main:app --reload --port 5000
```
4. 스키마 반영
- 앱 startup 시 SQLAlchemy로 자동 생성
- 수동 생성 시 `sql/schema.sql` 실행

## 8. 검증 스크립트
- PostgreSQL 연결 검증:
```bash
py scripts/verify_postgres.py
```
- Telegram 발송 검증:
```bash
py scripts/verify_telegram.py
```
- 파이프라인 E2E 실행:
```bash
py scripts/run_e2e_pipeline.py
```

## 9. 저장소 구조
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
    llm/
    pipeline/
    quality/
    signal/
  workers/
config/
prompts/
sql/
tests/
```

## 10. 현재 구현 범위와 확장 포인트
- 구현 완료:
  - FastAPI 엔드포인트
  - 파이프라인 오케스트레이터
  - 피처 계산, 신호 평가, 품질 게이트
  - Gemini 설명 생성기(ADC)
  - 텔레그램 알림 및 중복 억제
  - PostgreSQL 모델/DDL
  - 외부 커넥터 실연동 시도 로직(KIS/Naver/DART) + 실패 시 fallback
- 확장 예정:
  - X API/ECOS/KIND 연동 추가
  - 큐 기반 워커(Celery/Redis 등)로 분리
  - 뉴스 클러스터링/정정공시 체인/정량 DQ 리포트 강화

## 11. 현재 환경에서의 검증 결과
- 성공:
  - `py -m pytest -q tests` 통과
  - `py scripts/run_e2e_pipeline.py` 실행 성공(로컬 SQLite 기준)
  - FastAPI `POST /api/v1/analyze/ticker` 응답 200 확인(TestClient)
  - PostgreSQL 실접속 및 PostgreSQL 기반 E2E 확인
  - Telegram 실발송 성공(`http_status=200`)
- 미완료(환경값 필요):
  - 외부 API 실수집: `KIS_APP_KEY`, `DART_API_KEY`, `NAVER_CLIENT_ID/SECRET`, `X_BEARER_TOKEN` 미설정
