# 외부 데이터 연동 요구사항

## 핵심 분석 필수 키
- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- `OPEN_DART_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `DATABASE_URL`

## 한국 거시 / 정책 관련
- `BOK_API_KEY`
- `KOSIS_API_KEY`

## 글로벌 거시 / 뉴스 관련
- `FRED_API_KEY`
- `BLS_API_KEY`
- `BEA_API_KEY`
- `OECD_API_KEY`
- `WORLD_BANK_API_KEY`
- `IMF_API_KEY`
- `EUROSTAT_API_KEY`
- `NEWS_API_KEY`

## 알림 발송
- `TELEGRAM_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 제품별 활용 소스
### Market Regime
국내/글로벌 거시지표, 정책 문서, 섯터 광도, 글로벌 이슈를 활용합니다.

### Stock Decision
공통 분석 결과, 재무제표, 공시, 뉴스, 거시, 문서 요약을 활용합니다.

### Action Planner
Stock Decision 결과를 바탕으로 행동 구간, 시나리오, 실행 전제 조건을 생성합니다.

### Watchlist Alerts
점수 변화, 공시/정책 이벤트, 리스크 플래그, 알림 채널 설정을 활용합니다.
