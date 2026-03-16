# 공통 분석 엔진

## 1. 목적
`POST /api/v1/analyze/ticker`는 모든 사용자 제품의 공통 기반이 되는 핵심 분석 엔진입니다.

## 2. 입력
- `ticker_or_name`
- `as_of_date`
- `lookback_days`
- `analysis_mode`
- `notify`
- `force_send`
- `channels`
- `response_language`

## 3. 출력
- `features`
- `signal`
- `explanation`
- `alert`

## 4. 처리 흐름
1. 종목 정규화
2. 시세, 뉴스, 공시, 재무제표, 거시 데이터 수집
3. 문서 요약 및 신호 추출
4. 전처리 및 적재
5. feature 생성
6. signal 계산
7. explanation 생성
8. alert 판단

## 5. 현재 사용자 제품과의 관계
- `Market Regime`: 거시/가격/문서 흐름을 시장 수준으로 재구성
- `Stock Decision`: 공통 분석 결과를 종목 리포트로 재구성
- `Action Planner`: 종목 판단을 행동 계획으로 재구성
- `Watchlist Alerts`: 동일 기반 데이터를 현재 시점 점검 용도로 재구성

## 6. 문서화 이유
이 API 자체를 사용자가 직접 호출할 수는 있지만, 현재 프로젝트에서는 사용자 제품 리포트의 공통 엔진으로 보는 것이 더 정확합니다.
