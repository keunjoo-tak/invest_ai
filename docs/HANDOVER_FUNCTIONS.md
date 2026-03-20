# 인수인계 함수 및 로직 요약

## 1. 목적
이 문서는 현재 코드 기준으로 핵심 리포트가 어떤 함수와 어떤 데이터 흐름을 통해 만들어지는지 요약하기 위한 문서입니다.

## 2. 주요 진입점
- `app/main.py`: FastAPI 앱 생성, 인증 가드, 라우터 등록
- `app/api/routes/decision_products.py`: 사용자 제품 API 진입점
- `app/api/routes/analysis.py`: 공통 분석 엔진 API 진입점
- `app/services/pipeline/orchestrator.py`: 공통 분석 파이프라인 실행
- `app/services/intelligence/market_pulse.py`: `Market Regime` 조합 로직
- `app/services/intelligence/decision_products.py`: `Stock Decision`, `Action Planner`, `Watchlist Alerts` 조합 로직

## 3. Market Regime 생성 흐름
1. 거시 지표, 정책 문서, 글로벌 이슈, 헤드라인 뉴스, 리서치 문서를 수집한다.
2. 각 데이터를 정규화하고, 시장 체제 해석에 필요한 요약 구조로 변환한다.
3. 위험선호/중립/위험회피 상태를 계산한다.
4. 섹터 강약, 핵심 원인, 반증 조건, 최근 5일 헤드라인 영향, 리서치 체제 해석을 조합한다.
5. 웹 리포트에서는 섹션 카드 형태로 재배치한다.

## 4. Stock Decision 생성 흐름
1. 입력된 종목명 또는 티커를 종목 마스터에서 식별한다.
2. 시세, 뉴스, 공시, 재무제표, 섹터 모멘텀, 미국 야간 영향, 리서치 문서를 수집한다.
3. 뉴스는 종목 직접 언급 여부와 주가 영향 문맥을 기준으로 관련 기사만 남긴다.
4. 공시는 LLM/규칙 기반으로 호재·악재 점수화한다.
5. 재무제표는 성장성, 수익성, 안정성 비율로 변환한다.
6. 전체 특징 변수를 조합해 시그널 점수와 품질 점수를 계산한다.
7. 시장-섹터-종목 계층 점수와 기간별 해석을 만든다.
8. 웹 리포트에서는 상승/하락 요인, 이벤트 타임라인, 공시 카드, 재무/거시 근거, 리서치 컨센서스를 섹션으로 출력한다.

## 5. Action Planner 생성 흐름
1. `Stock Decision` 결과를 재사용한다.
2. 투자 기간, 위험 성향, 보유 여부, 평균 매입가, 투자 목적을 추가 반영한다.
3. 행동 결론, 가격 구간, 시나리오, 체크리스트를 생성한다.
4. 사용된 원문과 출처 링크를 함께 노출한다.

## 6. Watchlist Alerts 생성 흐름
1. 종목 분석 핵심 결과를 기반으로 즉시 점검 필요 여부를 계산한다.
2. 트리거와 리스크 플래그를 정리한다.
3. 원문 기사와 공시 출처를 함께 제공한다.
4. 구독 생성, 조회, 삭제 API를 통해 저장형 워치리스트를 관리한다.

## 7. 인증 및 외부 접속
- `app/api/routes/auth.py`: 로그인, 로그아웃, 세션 확인 API
- `app/services/auth/session_manager.py`: 세션 쿠키 생성/검증

## 8. 문서 유지 원칙
- 문서와 사용자 노출 문구는 한글을 우선 사용한다.
- 마크다운은 `UTF-8`, `BOM 없음`, `LF`를 유지한다.
- 기능 구조가 바뀌면 `README.md`, `docs/*.md`, `codex.md`를 함께 갱신한다.
- `run_investai_cloudrun_deploy.cmd`: Cloud Run ?? ?? ????
- `scripts/gcp/check_cloud_run_readiness.ps1`: Cloud Run ?? ?? ?? ??
