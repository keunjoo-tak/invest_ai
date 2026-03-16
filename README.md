# InvestAI

InvestAI는 `시장 체제 파악 -> 종목 판단 -> 행동 계획 -> 관찰 알림` 흐름으로 투자 의사결정을 지원하는 백엔드/API 기반 웹 서비스입니다.

## 1. 현재 서비스 구성
- 사용자 제품
  - `Market Regime`: 시장 체제, 거시 압력, 강세/약세 섹터 확인
  - `Stock Decision`: 개별 종목의 현재 판단, 상승/하락 요인, 타임라인 확인
  - `Action Planner`: 투자 기간과 위험 성향에 맞춘 실행 계획 생성
  - `Watchlist Alerts`: 관찰 종목 즉시 점검 및 저장형 워치리스트 관리
- 운영자 도구
  - `Source Preview`: 수집 소스 파싱 결과 미리보기
  - `Batch Execution`: 문서/거시/스냅샷 배치 실행
  - `Internal Probes`: 내부 커넥터 점검

## 2. 실행 방법
```powershell
cd D:\invest_ai
& D:\invest_ai\.venv\Scripts\Activate.ps1
py -m uvicorn app.main:app --host 127.0.0.1 --port 5000 --reload
```

- Swagger: `http://127.0.0.1:5000/docs`
- 웹 화면: `http://127.0.0.1:5000/app`
- 헬스체크: `http://127.0.0.1:5000/api/v1/health`

## 3. 사용자 사용 순서
1. `Market Regime`로 오늘 시장이 위험선호인지, 중립인지, 위험회피인지 확인합니다.
2. `Stock Decision`에 종목명 또는 티커를 넣고 현재 결론과 근거를 확인합니다.
3. 매매를 실제로 실행하려면 `Action Planner`에서 투자 기간과 위험 성향을 넣고 행동 계획을 봅니다.
4. 바로 매매하지 않을 종목은 `Watchlist Alerts`에 저장해 지속 관찰합니다.

## 4. 웹 화면에서 보이는 상태 정보
각 사용자 제품 카드에는 `pipeline_status`가 함께 표시됩니다.

- `메모리 캐시`: 최근 계산된 결과를 메모리 캐시에서 바로 반환한 상태
- `배치 스냅샷`: 미리 적재된 스냅샷을 사용한 상태
- `실시간 수집`: 외부 데이터 수집 후 즉시 계산한 상태
- `실시간 점검`: 워치리스트 점검처럼 호출 시점에 다시 계산한 상태

추가 표기
- `사전 계산 완료`: 배치 스냅샷이 준비되어 있음을 의미합니다.
- `스냅샷 생성 시각`: 마지막 배치 생성 시각입니다.
- `유효 시각`: 스냅샷 만료 시각입니다.

## 5. 시장 체제 스냅샷 파이프라인
첫 호출 지연을 줄이기 위해 시장 체제는 배치 스냅샷 파이프라인을 추가로 사용합니다.

### 5.1 흐름
1. 배치가 거시/섹터/대표 종목 데이터를 수집합니다.
2. `DecisionProductService.refresh_market_regime_snapshot()`이 시장 체제를 계산합니다.
3. 결과를 `product_snapshot_cache` 테이블에 저장합니다.
4. 웹/API의 `GET /api/v1/market-regime/overview`는 메모리 캐시가 없을 때 DB 스냅샷을 우선 조회합니다.
5. 스냅샷이 없을 때만 실시간 수집으로 시장 체제를 다시 계산합니다.

### 5.2 관련 엔드포인트
- `POST /api/v1/batch/market-regime-snapshot`
- `GET /api/v1/market-regime/overview`

### 5.3 스케줄러
- 매일 `07:10`에 시장 체제 스냅샷 배치가 실행되도록 설정했습니다.

## 6. 주요 엔드포인트
### 6.1 `GET /api/v1/market-regime/overview`
- 목적: 오늘 시장 체제와 섹터 흐름 파악
- 입력: 선택적 `as_of_date`
- 출력: 체제, 체제 점수, 전략 힌트, 강세/약세 섹터, 대표 종목, 파이프라인 상태
- 활용 데이터
  - 가격: KIS 일봉
  - 거시: BOK, KOSIS, OECD, FRED, BLS, BEA, Fiscal Data, World Bank, IMF, Eurostat
  - 문서: 정책브리핑, 한국은행, 글로벌/국제 거시 브리핑 배치 결과

### 6.2 `GET /api/v1/stock-decision/{ticker_or_name}`
- 목적: 개별 종목의 현재 판단과 근거 확인
- 입력: 종목명 또는 티커, 선택적 `as_of_date`, `lookback_days`
- 출력: 결론, 상태, 기간별 점수, 재무 요약, 거시 요약, 최근 이벤트 타임라인, 파이프라인 상태
- 활용 데이터
  - 시세: KIS
  - 뉴스: NAVER, NewsAPI
  - 공시: OpenDART, KIND
  - 재무제표: OpenDART 재무제표 API
  - 거시/정책: BOK, KOSIS, 정책브리핑, 글로벌 거시 데이터

### 6.3 `POST /api/v1/action-planner/analyze`
- 목적: 투자 성향과 기간에 맞춘 실행 계획 생성
- 입력: 종목, 투자 기간, 위험 성향, 보유 여부
- 출력: 권장 행동, 매수 관심 구간, 무효화 구간, 목표 구간, 시나리오, 파이프라인 상태
- 처리: `Stock Decision` 결과를 재가공하여 실행 문장으로 변환

### 6.4 `POST /api/v1/watchlist-alerts/check`
- 목적: 지금 즉시 대응이 필요한지 점검
- 입력: 종목, `notify`, `force_send`
- 출력: 즉시 알림 여부, 관찰 상태, 핵심 트리거, 리스크 플래그, 관찰 촉매, 파이프라인 상태
- 처리: 현재 시점 데이터를 다시 점검해 알림 가능성과 경계 요인을 계산

### 6.5 `POST /api/v1/watchlist-alerts/subscriptions`
- 목적: 저장형 워치리스트 등록
- 입력: 종목, 메모, 채널
- 출력: 구독 저장 결과

### 6.6 `POST /api/v1/batch/market-regime-snapshot`
- 목적: 시장 체제를 미리 계산해 저장
- 출력: 저장 경로, 수집/저장 건수, 배치 메시지

## 7. 배치와 저장 구조
- `product_snapshot_cache`
  - 목적: 시장 체제 같은 사용자 제품 응답을 사전 계산해 저장
  - 현재 사용: `market_regime`
- `watchlist_subscription`
  - 목적: 저장형 워치리스트 구독 상태 관리
- `external_document`
  - 목적: 정책브리핑, 한국은행, 글로벌 거시 브리핑 등 외부 문서 적재
- `release_calendar_event`
  - 목적: 공식 이벤트 캘린더 저장

## 4-1. 웹 대시보드 사용 방법
- 상단 서비스 카드의 버튼을 누르면 즉시 실행되거나, 오른쪽 슬라이드 입력 패널이 열립니다.
- 입력이 필요한 서비스
  - Stock Decision: 티커/종목명, 기준일, 조회 기간 입력
  - Action Planner: 티커/종목명, 투자 기간, 위험 성향, 보유 여부 입력
  - Watchlist Alerts: 티커/종목명, notify/force_send 옵션 입력
- 실행 결과는 각 서비스 카드 아래에 리포트 형식으로 출력됩니다.
- 리포트 첫 줄에는 최종 결론이 먼저 배치되고, 그 아래에 활용 데이터 요약, 근거 지표, 이벤트/정책/재무 근거가 표시됩니다.
- 워치리스트 저장은 Watchlist Alerts 카드의 워치리스트 저장 버튼으로 실행합니다.

## 8. 이번 변경 사항
- 시장 체제 스냅샷 배치 파이프라인 추가
- 웹 화면을 AI 기반 맞춤형 분석 대시보드로 재구성하고, 서비스 카드 아래에 리포트 형식 결과가 출력되도록 변경
- 입력이 필요한 서비스는 슬라이드 입력 패널에서 파라미터를 받고, 즉시 실행 서비스는 버튼만으로 동작하도록 조정
- 웹 화면에 캐시/스냅샷/실시간 수집 상태 표시 추가
- 사용자 제품 응답 문구를 한글 투자자 표현으로 정리
- `GET /api/v1/market-regime/overview`가 DB 스냅샷을 우선 사용하는 구조로 변경

## 9. 검증
```powershell
py -m compileall app tests
py -m pytest -q tests
```

- 결과: `15 passed`

## 10. 인코딩 규칙
- 모든 소스와 문서는 UTF-8로 저장합니다.
- 한글이 들어가는 파일은 PowerShell 출력이 아니라 파일 자체를 기준으로 검증합니다.
- 배포 전 아래 항목을 확인합니다.
  - BOM 없음
  - `U+FFFD` 없음
  - `연속 물음표` 패턴 없음

## 11. 종목 리포트 추가 근거
- `Stock Decision` 리포트에는 섹터 대장주와 peer 비교 표가 함께 포함됩니다.
- `Action Planner` 리포트에도 동일한 섹터 peer 근거가 함께 노출됩니다.
- 수시공시는 LLM 기반 `호재/악재/순효과/중요도` 점수로 즉시 요약됩니다.
  - 예: 공급계약, 유상증자, 전환사채 발행, 자사주, 배당
- quick 모드에서도 공시 점수화와 핵심 이벤트 요약은 유지됩니다.
- 주요 반영 feature
  - `disclosure_bullish_score`
  - `disclosure_bearish_score`
  - `disclosure_net_score`
  - `material_disclosure_severity`
  - `sector_peer_snapshot`
  - `event_volatility_score`
  - `event_pattern_bias`
  - `event_pattern_confidence`
  - `overnight_us_beta`
  - `overnight_us_signal`

## 2026-03-14 추가 반영 - 섹터 peer 비교와 수시공시 점수화
- `Stock Decision` 리포트에 섹터 대장주/peer 비교 표를 추가했습니다.
- `Action Planner` 리포트에도 섹터 모멘텀 근거와 peer 비교 표가 노출됩니다.
- 수시공시는 LLM을 통해 `bullish_score`, `bearish_score`, `net_score`, `event_severity`로 즉시 수치화됩니다.
- quick 모드에서도 공시 점수화가 수행되므로 사용자 제품 API 응답에 바로 반영됩니다.

