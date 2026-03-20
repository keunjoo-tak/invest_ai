# Cloud Run 배포 가이드

## 1. 목적
이 문서는 InvestAI를 Google Cloud Run에 배포하고, Cloud SQL과 Cloud Scheduler를 연결해 운영하는 절차를 정리한다.

## 2. 현재 운영 구성
현재 서비스는 아래 구성으로 동작한다.

- 애플리케이션 런타임: Cloud Run
- 컨테이너 빌드: Cloud Build
- 이미지 저장소: Artifact Registry
- 데이터베이스: Cloud SQL for PostgreSQL
- 정기 배치: Cloud Scheduler -> Cloud Run 내부 HTTP 엔드포인트 호출
- LLM 자격증명: Secret Manager에 저장된 Gemini ADC JSON 마운트

현재 배포 대상은 아래와 같다.

- 프로젝트: `investai-490800`
- 서비스명: `investai-api`
- 리전: `asia-northeast3`
- 서비스 URL: `https://investai-api-22138330969.asia-northeast3.run.app`

## 3. 자격증명 설계
### 3.1 배포용 자격증명
- 파일: `D:\invest_ai\investai-490800-3ec1fb014116.json`
- 용도: `gcloud` 인증, Cloud Run, Cloud Build, Secret Manager, Cloud SQL, Cloud Scheduler 제어

### 3.2 Gemini 호출용 자격증명
- 파일: `D:\invest_ai\pjt-dev-hdetrf-app-454403-db50d7f5f575.json`
- 용도: 애플리케이션 런타임에서 Gemini 호출
- 런타임 주입 방식: Secret Manager -> `/var/secrets/gemini/adc.json`

이 둘은 서로 다른 GCP 프로젝트에 속해 있으므로 코드와 배포 스크립트에서 명시적으로 분리했다.

## 4. Cloud SQL 구성
### 4.1 현재 생성된 자원
- 인스턴스명: `investai-pg`
- 연결명: `investai-490800:asia-northeast3:investai-pg`
- 리전: `asia-northeast3`
- 데이터베이스: `investai`
- 사용자: `investai`
- 비밀번호 시크릿: `investai-cloudsql-db-password`
- DB URL 시크릿: `investai-cloudsql-database-url`

### 4.2 프로비저닝 명령
```powershell
cd D:\invest_ai
.\run_investai_cloudsql_setup.cmd
```

실제 구현 스크립트는 `scripts/gcp/provision_cloud_sql.ps1`이다. 이 스크립트는 다음을 수행한다.

1. `sqladmin.googleapis.com` 등 필요한 API 활성화
2. Cloud SQL 인스턴스 생성 또는 재사용
3. 데이터베이스 생성
4. DB 사용자 생성 또는 비밀번호 갱신
5. 비밀번호 시크릿 생성 또는 갱신
6. `DATABASE_URL` 시크릿 생성 또는 갱신
7. 결과를 `logs/cloud_sql_latest.json`에 저장

## 5. Cloud Run 배포
### 5.1 배포 명령
```powershell
cd D:\invest_ai
.\run_investai_cloudrun_deploy.cmd
```

실제 구현 스크립트는 `scripts/gcp/deploy_cloud_run.ps1`이다.

### 5.2 배포 스크립트가 하는 일
1. 배포용 서비스 계정으로 인증
2. Cloud Run, Cloud Build, Artifact Registry, Secret Manager 등 필수 API 활성화
3. Artifact Registry 저장소 확인
4. Cloud Run 런타임 서비스 계정 확인
5. Gemini ADC 시크릿 반영
6. 컨테이너 이미지 빌드
7. Cloud Run 서비스 배포
8. 아래 시크릿을 런타임에 주입
   - `GEMINI_GOOGLE_APPLICATION_CREDENTIALS` -> `/var/secrets/gemini/adc.json`
   - `DATABASE_URL` -> `investai-cloudsql-database-url`
   - `SCHEDULER_SHARED_SECRET` -> `investai-scheduler-key`
9. Cloud SQL 인스턴스 연결 추가
10. 결과를 `logs/cloud_run_deploy_latest.json`에 저장

### 5.3 런타임 주요 값
- `SERVER_HOST=0.0.0.0`
- `SERVER_PORT=8080`
- `APP_ENV=cloudrun`
- `ENABLE_SCHEDULER=false`
- `DOWNLOADS_DIR=/tmp/downloads`
- `GEMINI_GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/gemini/adc.json`

## 6. Cloud Scheduler 구성
### 6.1 등록 명령
```powershell
cd D:\invest_ai
.\run_investai_scheduler_setup.cmd
```

실제 구현 스크립트는 `scripts/gcp/provision_cloud_scheduler.ps1`이다.

### 6.2 호출 구조
Cloud Scheduler는 Cloud Run 내부 HTTP 엔드포인트를 직접 호출한다.

- 목록 조회: `GET /api/v1/internal/scheduler/jobs`
- 작업 실행: `POST /api/v1/internal/scheduler/jobs/{job_id}`
- 보호 헤더: `X-InvestAI-Scheduler-Key`

공유 비밀은 Secret Manager의 `investai-scheduler-key` 시크릿으로 관리한다.

### 6.3 현재 작업 목록
- `public_research_global`
- `public_research_domestic`
- `policy_briefing`
- `bok_publications`
- `global_macro_briefings`
- `international_macro_briefings`
- `global_event_calendars`
- `global_issue_stream`
- `naver_headlines`
- `market_regime_snapshot`

스케줄 정의는 `app/workers/job_registry.py`에 있고, 로컬 APScheduler와 Cloud Scheduler가 같은 레지스트리를 사용한다.

## 7. 배포 전 점검
```powershell
cd D:\invest_ai
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gcp\check_cloud_run_readiness.ps1
```

점검 항목은 아래와 같다.

- 배포용 키 파일 존재 여부
- Gemini용 키 파일 존재 여부
- `.env` 핵심 값 존재 여부
- `gcloud` 실행 가능 여부
- 주요 스크립트 존재 여부

## 8. 검증 절차
### 8.1 헬스체크
```powershell
Invoke-WebRequest -UseBasicParsing https://investai-api-22138330969.asia-northeast3.run.app/api/v1/health | Select-Object -ExpandProperty Content
```

### 8.2 로그인 화면 확인
- `https://investai-api-22138330969.asia-northeast3.run.app/app/login`

### 8.3 인증 후 핵심 서비스 호출
- `GET /api/v1/market-regime/overview`
- `GET /api/v1/stock-decision/{ticker_or_name}`
- `POST /api/v1/action-planner/analyze`
- `POST /api/v1/watchlist-alerts/check`

### 8.4 배치 엔드포인트 검증
Cloud Scheduler 공유 비밀을 사용하면 아래 경로를 직접 검증할 수 있다.

- `POST /api/v1/internal/scheduler/jobs/market_regime_snapshot`

현재 기준 실검증 결과는 아래와 같다.

- Cloud SQL 연결 적용 후 Cloud Run `/api/v1/health` 응답 `200`
- 로그인 후 `GET /api/v1/market-regime/overview` 응답 `200`
- 내부 스케줄러 엔드포인트 `market_regime_snapshot` 실행 응답 `200`
- 자동 테스트 `43 passed`

## 9. 로그 및 산출물
- `logs/cloud_sql_latest.json`
- `logs/cloud_run_deploy_latest.json`
- `logs/cloud_scheduler_latest.json`

## 10. 운영 메모
- Cloud Run에서는 내부 APScheduler를 끄고 Cloud Scheduler만 사용한다.
- Cloud SQL은 비용이 발생하므로 미사용 시 중지 전략이 필요하다.
- `DATABASE_URL`은 시크릿으로만 관리하고 코드나 문서에 실제 비밀번호를 남기지 않는다.
- 런타임 서비스 계정에는 최소 아래 권한이 필요하다.
  - `roles/secretmanager.secretAccessor`
  - `roles/cloudsql.client`