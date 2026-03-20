## 인코딩 규칙
- 모든 소스와 문서는 UTF-8, BOM 없음, LF 기준으로 저장한다.
- PowerShell을 통해 한글 문서를 쓸 때는 UTF-8 인코딩을 명시한다.
- 문서 갱신 후에는 `U+FFFD`, 연속 물음표 4개 패턴, mojibake 패턴을 다시 점검한다.

## 2026-03-20 Cloud Run 전환
- 이전 공개 터널 관련 실행 스크립트, 문서, 바이너리를 제거했다.
- `GCP_DEPLOY_GOOGLE_APPLICATION_CREDENTIALS`와 `GEMINI_GOOGLE_APPLICATION_CREDENTIALS`를 분리해 배포 프로젝트와 LLM 프로젝트의 키를 나눠 쓰도록 구성했다.
- `Dockerfile`, `.dockerignore`, `.gcloudignore`, `scripts/gcp/check_cloud_run_readiness.ps1`, `scripts/gcp/deploy_cloud_run.ps1`, `run_investai_cloudrun_deploy.cmd`를 추가했다.
- Cloud Run 배포 시에는 `ENABLE_SCHEDULER=false`, `/tmp` 기준 다운로드 경로, SQLite fallback DB를 기본 설정으로 사용하도록 구성했다.
- `docs/CLOUD_RUN_DEPLOY.md`, `README.md`, `EXTERNAL_DATA_REQUIREMENTS.md`, `docs/HANDOVER_FUNCTIONS.md`를 Cloud Run 기준으로 갱신했다.
- Cloud Run 실제 배포를 완료했다.
- 배포 프로젝트는 `investai-490800`, 서비스는 `investai-api`, 리전은 `asia-northeast3`이다.
- 서비스 URL은 `https://investai-api-22138330969.asia-northeast3.run.app` 이다.
- 배포 검증으로 `/api/v1/health`, `/app/login`, 인증 후 `/api/v1/market-regime/overview`를 확인했다.
- `scripts/gcp/deploy_cloud_run.ps1`는 배포 결과를 `logs/cloud_run_deploy_latest.json`에 기록하도록 수정했다.
## 2026-03-20 Cloud SQL 및 Cloud Scheduler 전환
- Cloud Run 운영 구조를 SQLite fallback 중심 검증 단계에서 Cloud SQL 연동 구조로 확장했다.
- `scripts/gcp/provision_cloud_sql.ps1`와 `run_investai_cloudsql_setup.cmd`를 추가해 Cloud SQL 인스턴스, 데이터베이스, 사용자, Secret Manager 시크릿을 자동 준비하도록 구성했다.
- 현재 Cloud SQL 인스턴스는 `investai-pg`, 연결명은 `investai-490800:asia-northeast3:investai-pg`다.
- `scripts/gcp/deploy_cloud_run.ps1`를 수정해 Cloud Run 배포 시 `DATABASE_URL` 시크릿과 Cloud SQL 연결명을 함께 주입하도록 반영했다.
- `app/workers/job_registry.py`를 추가해 로컬 APScheduler와 Cloud Scheduler가 공통 작업 정의를 사용하도록 정리했다.
- `app/api/routes/scheduler_control.py`를 추가해 Cloud Scheduler 전용 HTTP 실행 엔드포인트를 구현했다.
- `scripts/gcp/provision_cloud_scheduler.ps1`와 `run_investai_scheduler_setup.cmd`를 추가해 Cloud Scheduler 작업을 자동 생성·갱신하도록 구성했다.
- 현재 등록된 배치 작업은 공개 리서치, 정책브리핑, 한국은행, 글로벌 거시 브리핑, 국제 거시 브리핑, 이벤트 캘린더, 글로벌 이슈 스트림, 네이버 헤드라인, 시장 체제 스냅샷까지 총 10개다.
- Cloud Scheduler 호출은 `X-InvestAI-Scheduler-Key` 공유 비밀 헤더로 보호된다.
- Cloud Run 재배포 후 `GET /api/v1/health`, 로그인, `GET /api/v1/market-regime/overview`, 내부 스케줄러 엔드포인트 호출까지 실검증했다.
- 테스트는 `py -m pytest -q tests` 기준 `43 passed`를 확인했다.
- 배포·프로비저닝 결과는 `logs/cloud_sql_latest.json`, `logs/cloud_run_deploy_latest.json`, `logs/cloud_scheduler_latest.json`에 기록하도록 유지했다.

## 2026-03-20 README 운영 가이드 보강
- `README.md`를 현재 Cloud Run, Cloud SQL, Cloud Scheduler 운영 구조 기준으로 재구성했다.
- 최초 구축, 일반 재배포, 스케줄 변경, DB 변경 상황별 실행 순서를 분리해 정리했다.
- 실시간 분석 파이프라인과 정기 배치 파이프라인이 언제, 어떻게 동작하는지 서비스 운영 관점으로 문서화했다.
- 배치 작업별 실행 시각, 동작 내용, 결과 사용처를 표로 정리했다.
- Cloud Run, Cloud SQL, Cloud Scheduler, Secret Manager, Gemini, 외부 API의 비용 발생 여부와 운영 메모를 README에 추가했다.

## 2026-03-20 Cloud Scheduler 헤더 플래그 수정
- `scripts/gcp/provision_cloud_scheduler.ps1`가 `gcloud scheduler jobs update http` 경로에서도 `--headers`를 사용하고 있어 기존 작업 갱신 시 실패하던 문제를 수정했다.
- `update http` 경로는 `--update-headers`를, `create http` 경로는 `--headers`를 사용하도록 분리했다.
- 수정 후 `run_investai_scheduler_setup.cmd`를 다시 실행해 Cloud Scheduler 작업 10개가 모두 정상 갱신되는 것을 확인했다.
