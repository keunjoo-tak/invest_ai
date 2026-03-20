# InvestAI

## 1. 개요
InvestAI는 한국 주식 투자 의사결정을 지원하는 AI 기반 분석 서비스다. 현재 서비스는 웹 대시보드와 FastAPI 백엔드를 중심으로 구성되어 있으며, 시장 체제 분석, 종목 판단, 행동 계획, 워치리스트 점검을 한 화면에서 제공한다.

주요 사용자 서비스는 아래 네 가지다.

- `Market Regime`: 시장 체제, 섹터 강약, 거시 환경, 헤드라인 뉴스, 리서치 근거를 종합해 현재 시장 대응 방향을 제시한다.
- `Stock Decision`: 개별 종목의 가격, 뉴스, 공시, 재무, 섹터 모멘텀, 거시 민감도를 결합해 매매 판단 리포트를 생성한다.
- `Action Planner`: 투자 기간, 위험 성향, 보유 여부를 반영해 실제 행동 계획을 제시한다.
- `Watchlist Alerts`: 관찰 종목의 즉시 점검 필요 여부와 핵심 트리거를 제공한다.

## 2. 현재 운영 구조
현재 프로젝트는 Google Cloud Platform 기준으로 아래 구조로 운영된다.

- 배포 프로젝트: `investai-490800`
- 서비스: Cloud Run
- 서비스명: `investai-api`
- 리전: `asia-northeast3`
- 운영 URL: `https://investai-api-22138330969.asia-northeast3.run.app`
- 로그인 페이지: `https://investai-api-22138330969.asia-northeast3.run.app/app/login`
- 헬스체크: `https://investai-api-22138330969.asia-northeast3.run.app/api/v1/health`
- 데이터베이스: Cloud SQL for PostgreSQL
- 정기 배치: Cloud Scheduler가 Cloud Run 내부 엔드포인트를 호출하는 방식
- LLM 호출: Gemini ADC를 Secret Manager로 마운트해서 사용

운영 관점의 핵심 원칙은 아래와 같다.

- 애플리케이션 실행은 Cloud Run이 담당한다.
- 영속 데이터 저장은 Cloud SQL이 담당한다.
- 정기 수집과 스냅샷 생성은 Cloud Scheduler가 담당한다.
- 배포용 GCP 자격증명과 Gemini 호출용 자격증명은 반드시 분리한다.

## 3. 인증 정보 분리 원칙
이 프로젝트는 배포용 GCP 자격증명과 LLM 호출용 GCP 자격증명을 분리해서 사용한다.

### 3.1 배포용 자격증명
- 목적: `gcloud`, Cloud Build, Artifact Registry, Cloud Run, Secret Manager, Cloud SQL, Cloud Scheduler 제어
- 파일: `D:\invest_ai\investai-490800-3ec1fb014116.json`
- 대상 프로젝트: `investai-490800`

### 3.2 Gemini 호출용 자격증명
- 목적: 애플리케이션 런타임에서 Gemini 호출
- 파일: `D:\invest_ai\pjt-dev-hdetrf-app-454403-db50d7f5f575.json`
- 대상 프로젝트: `pjt-dev-hdetrf-app-454403`

애플리케이션은 `GEMINI_GOOGLE_APPLICATION_CREDENTIALS` 또는 Cloud Run 시크릿 마운트 경로만 사용해서 LLM을 호출한다. 배포용 ADC와 LLM용 ADC가 섞이지 않도록 코드와 배포 스크립트를 분리해 두었다.

## 4. 로컬 실행 방법
### 4.1 서버 실행
```powershell
cd D:\invest_ai
.\run_investai_server.cmd
```

기본 접속 주소는 아래와 같다.

- 웹: `http://127.0.0.1:5000/app/login`
- Swagger: `http://127.0.0.1:5000/docs`
- 헬스체크: `http://127.0.0.1:5000/api/v1/health`

### 4.2 같은 네트워크의 다른 기기에서 접속
로컬 서버는 `0.0.0.0:5000`에 바인딩되도록 설정되어 있다. 따라서 같은 Wi-Fi 또는 LAN 안에 있는 모바일, 노트북에서는 아래 형태로 접속하면 된다.

- 웹: `http://<내-PC-LAN-IP>:5000/app/login`
- Swagger: `http://<내-PC-LAN-IP>:5000/docs`

## 5. 배포 실행 순서
이 프로젝트는 상황에 따라 실행해야 하는 스크립트가 다르다. 항상 세 개를 모두 실행하는 구조는 아니다.

### 5.1 최초 1회 구축
최초로 Cloud Run 운영 환경을 만드는 경우에는 아래 순서를 권장한다.

1. `run_investai_cloudsql_setup.cmd`
2. `run_investai_cloudrun_deploy.cmd`
3. `run_investai_scheduler_setup.cmd`

각 단계의 의미는 아래와 같다.

1. Cloud SQL 인스턴스, 데이터베이스, 사용자, 시크릿을 먼저 준비한다.
2. 애플리케이션을 Cloud Run에 배포한다.
3. 정기 배치를 Cloud Scheduler에 등록한다.

### 5.2 평소 코드만 수정해서 재배포할 때
일반적인 코드 수정 배포는 아래만 실행하면 된다.

```powershell
cd D:\invest_ai
.\run_investai_cloudrun_deploy.cmd
```

이 경우 Cloud SQL과 Cloud Scheduler는 기존 자원을 그대로 재사용한다.

### 5.3 스케줄 정의만 바뀌었을 때
배치 시간, 작업 목록, 스케줄러 엔드포인트가 바뀌었다면 아래를 실행한다.

```powershell
cd D:\invest_ai
.\run_investai_scheduler_setup.cmd
```

애플리케이션 코드도 같이 바뀌었다면 그 다음에 `run_investai_cloudrun_deploy.cmd`를 실행한다.

### 5.4 DB 연결 구조만 바뀌었을 때
Cloud SQL 인스턴스, 데이터베이스, DB 사용자, 비밀번호 시크릿, `DATABASE_URL` 시크릿을 바꿨다면 아래 순서를 사용한다.

1. `run_investai_cloudsql_setup.cmd`
2. `run_investai_cloudrun_deploy.cmd`

### 5.5 실행 순서 요약
- 코드 변경만 있음: `run_investai_cloudrun_deploy.cmd`
- DB 준비 또는 변경 있음: `run_investai_cloudsql_setup.cmd` 후 `run_investai_cloudrun_deploy.cmd`
- 스케줄 변경 있음: `run_investai_scheduler_setup.cmd`
- 최초 구축: 세 개 모두 순서대로 실행

## 6. 각 스크립트가 하는 일
### 6.1 `run_investai_cloudsql_setup.cmd`
실제 구현은 `scripts/gcp/provision_cloud_sql.ps1`이다.

이 스크립트는 아래를 수행한다.

- Cloud SQL API 활성화
- 인스턴스 생성 또는 재사용
- 데이터베이스 생성 또는 재사용
- DB 사용자 생성 또는 비밀번호 갱신
- DB 비밀번호 시크릿 생성 또는 갱신
- Cloud Run용 `DATABASE_URL` 시크릿 생성 또는 갱신
- 결과를 `logs/cloud_sql_latest.json`에 기록

현재 기준 Cloud SQL 자원은 아래와 같다.

- 인스턴스명: `investai-pg`
- 연결명: `investai-490800:asia-northeast3:investai-pg`
- 데이터베이스명: `investai`
- 사용자명: `investai`
- 비밀번호 시크릿: `investai-cloudsql-db-password`
- DB URL 시크릿: `investai-cloudsql-database-url`

### 6.2 `run_investai_cloudrun_deploy.cmd`
실제 구현은 `scripts/gcp/deploy_cloud_run.ps1`이다.

이 스크립트는 아래를 수행한다.

1. 배포용 서비스 계정으로 `gcloud auth activate-service-account` 수행
2. 필요한 GCP API 활성화
3. Artifact Registry 저장소 확인
4. Cloud Run 런타임 서비스 계정 확인
5. Gemini ADC를 Secret Manager에 반영
6. 컨테이너 이미지 빌드
7. Cloud Run 서비스 배포
8. Cloud SQL 연결 및 시크릿 기반 `DATABASE_URL` 주입
9. Scheduler 공유 비밀 시크릿 주입
10. 결과를 `logs/cloud_run_deploy_latest.json`에 기록

### 6.3 `run_investai_scheduler_setup.cmd`
실제 구현은 `scripts/gcp/provision_cloud_scheduler.ps1`이다.

이 스크립트는 아래를 수행한다.

- Cloud Scheduler API 활성화
- 스케줄러 공유 비밀 시크릿 생성 또는 재사용
- Cloud Run 서비스 URL 확인
- 공통 작업 레지스트리에서 작업 정의 읽기
- 작업별 HTTP Scheduler 생성 또는 갱신
- 결과를 `logs/cloud_scheduler_latest.json`에 기록

## 7. 운영 기준 파이프라인 동작 방식
InvestAI의 파이프라인은 크게 두 종류다.

- 요청 시 실시간으로 동작하는 분석 파이프라인
- 정해진 시간에 동작하는 배치 파이프라인

### 7.1 요청 시 실시간 파이프라인
#### `Market Regime`
- 실행 시점: 사용자가 `Market Regime` 화면을 열거나 API를 호출할 때
- 주요 입력: 기준일, 인증 세션
- 주요 처리:
  - 시장, 거시, 이벤트, 헤드라인, 리서치 스냅샷 조회
  - 필요한 경우 라이브 수집 또는 캐시 재사용
  - 시장 체제 점수, 섹터 강약, 핵심 근거 생성
- 주요 출력: 시장 체제 리포트, 섹터 강약, 헤드라인 영향, 리서치 근거
- 자동 실행 여부: 사용자가 호출할 때만 실행

#### `Stock Decision`
- 실행 시점: 사용자가 종목 입력 후 리포트 생성 버튼을 누를 때
- 주요 입력: 종목명 또는 티커
- 주요 처리:
  - 종목 식별
  - 시세, 뉴스, 공시, 재무, 섹터 모멘텀, 거시 민감도 수집
  - 특징 생성, 시그널 점수 계산, 리포트 조합
- 주요 출력: 종목 판단 리포트, 상승/하락 요인, 이벤트 타임라인, 근거 문서
- 자동 실행 여부: 사용자가 호출할 때만 실행

#### `Action Planner`
- 실행 시점: 사용자가 조건 입력 후 행동 계획 생성 버튼을 누를 때
- 주요 입력: 종목, 투자 기간, 위험 성향, 보유 여부, 평균단가
- 주요 처리:
  - 내부적으로 `Stock Decision` 분석 호출
  - 시나리오, 행동 점수, 진입/관찰/보유 전략 생성
- 주요 출력: 행동 계획 리포트
- 자동 실행 여부: 사용자가 호출할 때만 실행

#### `Watchlist Alerts`
- 실행 시점: 사용자가 단건 점검 또는 저장된 워치리스트 조회를 수행할 때
- 주요 입력: 종목, 채널, 저장 여부
- 주요 처리:
  - 종목 분석 결과 재사용 또는 재계산
  - 즉시 점검 필요 여부와 트리거 계산
- 주요 출력: 알림 판단, 핵심 트리거, 리스크 플래그
- 자동 실행 여부: 사용자가 호출할 때만 실행

### 7.2 정기 배치 파이프라인
Cloud Run에서는 내부 APScheduler를 끄고, Cloud Scheduler가 HTTP 호출로 아래 작업을 수행한다.

| 작업 ID | 실행 시각(Asia/Seoul) | 동작 내용 | 결과 사용처 |
| --- | --- | --- | --- |
| `public_research_global` | 05:15 | 글로벌 공개 리서치 문서 수집 및 정규화 | Market Regime, Stock Decision |
| `public_research_domestic` | 06:00 | 국내 증권사·은행 리서치 문서 수집 및 정규화 | Market Regime, Stock Decision |
| `policy_briefing` | 06:15 | 정책브리핑 문서 수집 및 적재 | Market Regime, 개별 종목 거시 근거 |
| `bok_publications` | 06:35 | 한국은행 자료 수집 및 적재 | Market Regime, 거시 근거 |
| `global_macro_briefings` | 06:50 | 미국·글로벌 거시 브리핑 생성 | Market Regime |
| `international_macro_briefings` | 06:53 | 국제 거시 브리핑 생성 | Market Regime |
| `global_event_calendars` | 06:55 | 공식 이벤트 캘린더 수집 | Market Regime, 이벤트 주의 모드 |
| `global_issue_stream` | 07:05 | 글로벌 이슈 스트림 수집 | Market Regime, 종목 거시 민감도 |
| `naver_headlines` | 07:07 | 네이버 섹션 헤드라인 수집 및 요약 | Market Regime |
| `market_regime_snapshot` | 07:10 | 시장 체제 스냅샷 생성 | Market Regime 초기 응답 속도 개선 |

배치 파이프라인의 공통 구조는 아래와 같다.

1. Cloud Scheduler가 Cloud Run 내부 엔드포인트 호출
2. 공유 비밀 검증
3. 해당 배치 수집기 실행
4. 원문, 메타, 요약 정규화
5. DB 적재 또는 캐시 스냅샷 생성
6. 다음 사용자 요청에서 재사용

## 8. 운영 관점에서 서비스가 언제 동작하는지
### 8.1 사용자가 요청할 때만 동작하는 기능
- `Market Regime`
- `Stock Decision`
- `Action Planner`
- `Watchlist Alerts`
- `Source Preview`
- 배치 실행 화면의 수동 실행 버튼

### 8.2 정해진 시간에 자동으로 동작하는 기능
- 공개 리서치 수집
- 정책브리핑 수집
- 한국은행 자료 수집
- 거시 브리핑 생성
- 이벤트 캘린더 수집
- 글로벌 이슈 스트림 수집
- 네이버 헤드라인 수집
- 시장 체제 스냅샷 생성

즉, 사용자 화면에서 리포트를 보지 않아도 배치 파이프라인은 Cloud Scheduler 기준으로 계속 동작한다.

## 9. 비용 발생 여부와 운영 메모
정확한 금액은 사용량과 GCP 요금제에 따라 달라지므로 여기서는 비용 발생 여부와 발생 시점을 운영 관점으로 정리한다.

| 구성 요소 | 비용 발생 여부 | 언제 비용이 생기는가 | 운영 메모 |
| --- | --- | --- | --- |
| 로컬 실행 | 보통 없음 | 사용자 PC 자원만 사용 | 클라우드 비용 없음 |
| Cloud Run | 발생 | 요청 처리, CPU/메모리 사용, 네트워크 egress, 로그 | 사용량이 늘수록 비용 증가 |
| Cloud Build | 발생 | 배포할 때마다 이미지 빌드 수행 시 | 코드 변경 후 재배포 횟수와 연동 |
| Artifact Registry | 발생 | 컨테이너 이미지 저장 시 | 오래된 이미지 정리 필요 |
| Cloud SQL | 발생 | 인스턴스가 살아 있는 동안, 스토리지/백업 사용 시 | 가장 상시 비용 성격이 강함 |
| Cloud Scheduler | 발생 가능 | 작업 수와 호출량에 따라 과금 구간 진입 가능 | 현재 10개 작업 등록 |
| Secret Manager | 발생 가능 | 시크릿 버전 저장 및 액세스 횟수 증가 시 | 버전 누적 관리 필요 |
| Gemini / Vertex AI | 발생 | LLM 호출 시 | 분석 요청량과 배치 요약량에 비례 |
| 외부 유료 API | 계정 정책에 따라 다름 | 호출량 또는 요금제 한도 초과 시 | NewsAPI, 증권 API 약관 확인 필요 |

### 9.1 비용이 특히 크게 나는 구간
- Cloud SQL 인스턴스를 계속 켜 두는 구간
- Cloud Run 재배포가 잦아서 Cloud Build가 자주 도는 구간
- 배치 요약과 리포트 번역 등 Gemini 호출이 많은 구간
- 문서 원문 저장량이 커져 추가 스토리지 전략이 필요한 구간

### 9.2 비용 절감 운영 팁
1. 코드 변경이 없으면 `run_investai_cloudrun_deploy.cmd`를 반복 실행하지 않는다.
2. 배치 시간이 과도하면 `app/workers/job_registry.py` 기준으로 조정한다.
3. 불필요한 리서치나 문서 수집 범위를 줄인다.
4. Cloud SQL은 상시 운영이 꼭 필요한지 주기적으로 점검한다.
5. 오래된 이미지와 시크릿 버전은 주기적으로 정리한다.

## 10. 일상 운영 가이드
### 10.1 매일 확인할 항목
1. `GET /api/v1/health`가 `200`인지 확인
2. 로그인 후 `Market Regime`가 정상 렌더링되는지 확인
3. `logs/cloud_scheduler_latest.json` 기준 스케줄러 구성이 맞는지 확인
4. Cloud Run 로그에 시작 실패나 인증 오류가 없는지 확인
5. Cloud SQL 연결 오류가 없는지 확인

### 10.2 코드 수정 후 배포 체크리스트
1. 로컬 테스트 수행
2. `run_investai_cloudrun_deploy.cmd` 실행
3. `/api/v1/health` 확인
4. 로그인 후 핵심 서비스 1회 이상 호출
5. 필요하면 Scheduler 작업 재동기화

### 10.3 배치 스케줄 변경 체크리스트
1. `app/workers/job_registry.py` 수정
2. `run_investai_scheduler_setup.cmd` 실행
3. Cloud Scheduler 콘솔 또는 로그 파일에서 반영 확인
4. 필요 시 수동 트리거로 단건 검증

### 10.4 DB 변경 체크리스트
1. Cloud SQL 관련 `.env` 값 검토
2. `run_investai_cloudsql_setup.cmd` 실행
3. `run_investai_cloudrun_deploy.cmd` 실행
4. 애플리케이션 헬스체크와 로그인 후 분석 API 확인

## 11. 검증 방법
### 11.1 로컬 검증
```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/api/v1/health | Select-Object -ExpandProperty Content
```

### 11.2 Cloud Run 검증
```powershell
Invoke-WebRequest -UseBasicParsing https://investai-api-22138330969.asia-northeast3.run.app/api/v1/health | Select-Object -ExpandProperty Content
```

### 11.3 자동 테스트
```powershell
cd D:\invest_ai
py -m pytest -q tests
```

현재 기준 테스트 결과는 `43 passed`다.

## 12. 주요 로그 파일
- `logs/cloud_sql_latest.json`: Cloud SQL 프로비저닝 결과
- `logs/cloud_run_deploy_latest.json`: 최신 Cloud Run 배포 결과
- `logs/cloud_scheduler_latest.json`: 최신 Cloud Scheduler 작업 구성 결과

## 13. 관련 문서
- `docs/CLOUD_RUN_DEPLOY.md`: Cloud Run, Cloud SQL, Cloud Scheduler 배포 상세 문서
- `docs/DATA.md`: 수집 및 활용 데이터 정리
- `docs/HANDOVER_FUNCTIONS.md`: 리포트 계산 로직 및 함수 설명
- `docs/FEATURE_MARKET_REGIME.md`: Market Regime 화면과 로직 설명
- `docs/FEATURE_STOCK_DECISION.md`: Stock Decision 화면과 로직 설명
- `docs/FEATURE_ACTION_PLANNER.md`: Action Planner 화면과 로직 설명
