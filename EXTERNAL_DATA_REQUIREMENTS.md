# 외부 연동 요구사항

## 1. 필수 공통 설정
### 1.1 애플리케이션 및 인증
- `GOOGLE_APPLICATION_CREDENTIALS`: Gemini ADC 인증에 사용할 서비스 계정 JSON 경로
- `DATABASE_URL`: PostgreSQL 연결 문자열
- `AUTH_ENABLED`: 인증 사용 여부
- `AUTH_USERNAME`: 웹 로그인 사용자명
- `AUTH_PASSWORD`: 웹 로그인 비밀번호
- `AUTH_SECRET_KEY`: 세션 쿠키 서명 키
- `AUTH_SESSION_MAX_AGE_SECONDS`: 세션 유지 시간

### 1.2 서버 노출 설정
- `SERVER_HOST`: 기본 바인딩 호스트
- `SERVER_PORT`: 기본 포트
- `CORS_ALLOWED_ORIGINS`: 허용 오리진 목록
- `TRUSTED_HOSTS`: 허용 호스트 목록

## 2. 종목 분석 데이터
### 2.1 시세 및 종목 정보
- `KIS_APP_KEY`
- `KIS_APP_SECRET`

### 2.2 공시 및 재무제표
- `OPEN_DART_API_KEY`

### 2.3 뉴스
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `NEWS_API_KEY`

### 2.4 알림
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_ENABLED`

## 3. 국내 거시 및 정책 데이터
- `BOK_API_KEY`
- `KOSIS_API_KEY`

정책브리핑, 한국은행 공개 페이지, 네이버 섹션 헤드라인은 공개 웹 기반 수집이므로 별도 API 키가 없는 경로도 존재합니다.

## 4. 글로벌 거시 데이터
- `OECD_API_KEY`
- `FRED_API_KEY`
- `BLS_API_KEY`
- `BEA_API_KEY`
- `FISCAL_DATA_API_KEY`
- `IMF_API_KEY`
- `WORLD_BANK_API_KEY`
- `EUROSTAT_API_KEY`

일부 API는 공개 호출도 가능하지만, 운영 안정성과 호출 한도 관리를 위해 키 설정을 권장합니다.

## 5. 공개 리서치 및 문서 수집
다음 범주의 공개 문서는 현재 배치 파이프라인으로 수집합니다.

- 국내 증권사 공개 리포트
- 국내 은행 및 연구소 공개 리포트
- 글로벌 자산운용사 및 투자전략 리포트
- 정책브리핑, 한국은행 자료
- 네이버 뉴스 섹션 헤드라인

대부분 공개 페이지 기반 수집이므로 별도 계정이 없는 소스도 많습니다. 다만 페이지 구조 변경에 취약할 수 있어 정기 점검이 필요합니다.

## 6. 운영 시 확인 사항
- `.env`에 민감 정보가 모두 존재하는지 확인합니다.
- 배치 실행 전 `DATABASE_URL`과 Google ADC 경로가 유효한지 확인합니다.
- Cloud Run ?? ??? `docs/CLOUD_RUN_DEPLOY.md`? `scripts/gcp/check_cloud_run_readiness.ps1` ??? ?? ?????.
