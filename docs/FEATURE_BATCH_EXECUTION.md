# Batch Execution

## 1. 목적
`Batch Execution`은 문서, 거시 데이터, 이벤트 캘린더, 시장 체제 스냅샷을 미리 적재하는 운영자 기능입니다.

## 2. 주요 배치
- `POST /api/v1/batch/kind/disclosures`
- `POST /api/v1/batch/policy-briefing`
- `POST /api/v1/batch/bok/publications`
- `POST /api/v1/batch/global-macro-briefings`
- `POST /api/v1/batch/international-macro-briefings`
- `POST /api/v1/batch/global-event-calendars`
- `POST /api/v1/batch/global-issue-stream`
- `POST /api/v1/batch/market-regime-snapshot`

## 3. 시장 체제 스냅샷 배치
### 목적
- `Market Regime` 첫 호출 지연을 줄이기 위해 시장 체제를 미리 계산해 저장합니다.

### 처리 흐름
1. 가격, 거시, 문서 기반으로 시장 체제를 계산합니다.
2. 결과를 `product_snapshot_cache`에 저장합니다.
3. 결과 JSON을 호출 단위 폴더에도 저장합니다.
4. 이후 `GET /api/v1/market-regime/overview`는 스냅샷을 우선 사용합니다.

### 사용자 체감 효과
- 첫 호출이 실시간 수집보다 훨씬 빨라질 수 있습니다.
- 웹 리포트에 `배치 스냅샷` 상태가 표시됩니다.

## 4. 운영자 관점 체크 포인트
- 배치가 정상 완료되었는지
- 저장 경로가 남았는지
- 문서/거시 데이터가 실제로 적재되었는지
- 시장 체제 스냅샷의 생성 시각과 유효 시각이 적절한지
