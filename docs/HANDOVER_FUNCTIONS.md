# 인수인계 문서

## 1. 문서 목적
- 이 문서는 `Market Regime`, `Stock Decision` 리포트에 표시되는 핵심 점수, 판단, 요인, 기울기, 비중, 경고가 어떤 데이터와 계산 로직으로 만들어지는지 설명한다.
- 목적은 두 가지다.
  - 사용자에게 왜 이런 결과가 나왔는지 명확한 근거를 설명할 수 있게 한다.
  - 개발자와 운영자가 화면 값과 실제 계산 코드를 바로 연결해 추적할 수 있게 한다.

## 2. 공통 원칙
- 리포트에 보이는 모든 문장과 점수는 실제 데이터 또는 실제 계산 결과에 기반해야 한다.
- 내부 판정 코드와 사용자 노출 라벨은 분리한다.
  - 예: 내부 코드 `EVENT_MONITOR`, 사용자 표시 `이벤트 관찰`
- 종목은 항상 `종목명(ticker)` 형식으로 표기한다.
- 설명용 웹 파생 점수는 반드시 API 응답값에서 다시 계산할 수 있어야 한다.

## 3. 책임 경로

### 3.1 Market Regime
- 백엔드 계산
  - `app/services/intelligence/market_pulse.py`
    - `MarketPulseEngine.overview()`
    - `MarketPulseEngine._classify_regime()`
- 제품 응답 조립
  - `app/services/intelligence/decision_products.py`
    - `DecisionProductService.build_market_regime()`
    - `DecisionProductService.refresh_market_regime_snapshot()`
- 웹 리포트 파생 계산
  - `app/web/app.js`
    - `deriveMarketRegimeContext()`
    - `marketSummaryText()`
    - `regimeConfidenceLabel()`
    - `regimeDirectionLabel()`
    - `renderMarketReport()`

### 3.2 Stock Decision
- feature 생성
  - `app/services/features/feature_builder.py`
    - `build_features()`
    - `build_event_pattern_snapshot()`
- 시그널 계산
  - `app/services/signal/scorer.py`
    - `evaluate_signal()`
- 품질 게이트
  - `app/services/quality/gates.py`
    - `passes_quality_gate()`
- 제품 응답 조립
  - `app/services/intelligence/decision_products.py`
    - `DecisionProductService.build_stock_decision()`
    - `_component_scores()`
    - `_horizon_scores()`
    - `_state_label()`
    - `_relative_strength()`
    - `_bullish_factors()`
    - `_bearish_factors()`
    - `_timeline()`
    - `_sector_momentum_summary()`
    - `_sector_peer_snapshot()`
    - `_financial_summary()`
    - `_macro_summary()`
    - `_event_pattern_summary()`
- 웹 리포트 파생 계산
  - `app/web/app.js`
    - `deriveStockDecisionContext()`
    - `dominantStockHorizon()`
    - `stockValidityWindow()`
    - `stockChangedVariables()`
    - `stockConflictSignals()`
    - `stockPeriodNarratives()`
    - `stockLayerNarratives()`
    - `stockTechnicalWarnings()`
    - `stockMacroSensitivity()`
    - `splitDocumentSummaries()`
    - `renderStockReport()`

## 4. Market Regime 리포트 근거 문서화

### 4.1 원천 데이터
| 데이터 구분 | 원천 | 실제 사용 필드 | 사용 목적 |
| --- | --- | --- | --- |
| 대표 종목 가격 일봉 | KIS | 최근 60일 `close` | 시장 평균 20일 수익률, 대표 종목 변동성, 섹터 점수 계산 |
| 종목-섹터 매핑 | `MarketPulseEngine._sector_map` | `ticker -> sector` | 섹터별 평균 수익률/변동성 계산 |
| 거시 스냅샷 | `fetch_macro()` | `surprise_std`, `actual`, `indicator_name`, `country` | 시장 체제 점수, 핵심 거시 변수, 글로벌 리스크 설명 |
| 정책/문서 힌트 | `external_document` | `source_system`, `title`, `summary_json.summary` | 전략 힌트, 정책/문서 근거 문장 생성 |
| 응답 상태 | 메모리 캐시, 배치 스냅샷, 실시간 수집 | `pipeline_status` | 신선도, 생성 경로, 응답 신뢰도 표시 |

### 4.2 핵심 계산식
- 종목 20일 수익률
  - `ret20 = (마지막 종가 / 20거래일 전 종가) - 1`
- 종목 20일 변동성 프록시
  - `vol20 = (최근 20일 최고 종가 - 최근 20일 최저 종가) / 최근 20일 최고 종가`
- 섹터 점수
  - `sector_score = (sector_ret * 100) - (sector_vol * 30)`
- 평균 거시 압력
  - `macro_pressure = mean(surprise_std)`
- 시장 체제 점수
  - `regime_score = (avg_ret20 * 100) - (avg_vol20 * 50) - (macro_pressure * 20)`
- 체제 분류
  - `regime_score >= 2.5` -> `위험선호`
  - `regime_score <= -2.5` -> `위험회피`
  - 그 외 -> `중립`

### 4.3 리포트 항목별 근거
#### 상단 핵심 결론
- 체제
  - `data.regime`
- 한 줄 결론
  - `marketSummaryText()`가 `regime`, 선도 섹터, 확신도를 조합해 생성한다.
- 체제 기울기
  - `regimeDirectionLabel(data.regime_score)`
- 현재 확신도
  - `regimeConfidenceLabel(data.regime_score, risingRatio)`
- 기준일 / 데이터 반영 시각 / 시장 구간 / 응답 경로
  - `as_of_date`, `generated_at_utc`, `pipeline_status`

#### 요약 KPI 4개
- 시장 체제 점수
  - `data.regime_score`
- 체제 기울기
  - `regimeDirectionLabel()`
- 현재 확신도
  - `regimeConfidenceLabel()`
- 대표 종목 상승 비중
  - `positive representatives / total representatives * 100`

#### 시장 체제 분해
- 종합 체제
  - `clamp(50 + regime_score * 6)`
- 가격/추세
  - `clamp(50 + avgRet * 3.2 + breadthDelta * 4)`
- 변동성
  - `clamp(100 - avgVol * 4.5)`
- 유동성/금리 압력
  - `clamp(55 - average(macroScores) * 10)`
- 정책 우호도
  - `clamp(48 + strategy_hints.length * 3)`
- 글로벌 리스크
  - `clamp(50 + mean(abs(macroScores)) * 10)`
- breadth
  - `clamp(risingRatio * 100)`
- 의미
  - 웹이 사용자의 이해를 돕기 위해 0~100 스케일로 다시 표현한 설명용 점수다.

#### 핵심 원인 Top 5
- 상승 동인
  - 강세 섹터 상위 3개 + 양(+) 거시 row 상위 2개
- 하락/제약 동인
  - 약세 섹터 하위 3개 + 음(-) 거시 row 상위 2개
- 민감 거시 변수
  - `abs(surprise_std)` 기준 상위 3개
- 최근 체제 해석 힌트
  - `strategy_hints` 앞 5개

#### 섹터 판단
- 강세 섹터 Top N
  - `strong_sectors`
- 약세 섹터 Bottom N
  - `weak_sectors`
- 대표 종목 근거
  - `representative_symbols`
  - 화면에서는 `종목명(ticker): 20일 수익률, 변동성` 형식으로 표시

#### 투자자 행동 연결
- `actionGuide`는 체제별 정적 규칙을 사용한다.
  - 위험선호 -> 선도 섹터 중심 접근
  - 위험회피 -> 방어적 운영
  - 중립 -> 선별 대응
- 이 영역은 새 점수를 만드는 단계가 아니라 체제 해석을 행동 언어로 번역하는 단계다.

#### 반증 조건
- 무효화 조건
  - 금리 surprise 확대, 환율 급등, 정책 기대 후퇴 등 고정 규칙
- 재확인할 거시 항목
  - `sensitiveMacro`
- 체제 전환 신호
  - breadth 약화, macro surprise 연속, 선도 섹터 붕괴 같은 규칙 기반 문구

#### 신뢰도 및 데이터 설명
- 가격, 거시, 정책/문서, 응답 경로, 최신성, 한계를 함께 보여준다.
- breadth와 섹터 판단은 대표 종목 기반 프록시라는 점을 명시한다.

## 5. Stock Decision 리포트 근거 문서화

### 5.1 원천 데이터
| 데이터 구분 | 원천 | 실제 사용 필드 | 사용 목적 |
| --- | --- | --- | --- |
| 가격 일봉 | KIS | `open`, `high`, `low`, `close`, `volume` | MA, RSI, 수익률, 거래량, ATR, 갭 수익률 계산 |
| 뉴스 | NAVER, NewsAPI | `title`, `content_text`, `sentiment_score`, `attention_score` | 뉴스 감성, 주목도, 타임라인, 상승/하락 근거 |
| 공시 | OpenDART, KIND | `event_type`, `impact_score`, `material_disclosure_*` | 공시 호재/악재 점수, 이벤트 점수 |
| 재무제표 | OpenDART | `revenue_growth_yoy`, `operating_margin`, `net_margin`, `debt_ratio`, `current_ratio`, `operating_cashflow_margin` | 재무/실적/가치 판단 |
| 거시 데이터 | 국내외 거시 커넥터 | `surprise_index`, `surprise_std`, `macro_risk_score`, `macro_support_score` | 시장 영향, 종목 관련 거시 근거 |
| 섹터 모멘텀 | 내부 계산 | `sector_coupling_score`, `sector_fund_flow_score`, `sector_breadth_score`, `sector_leader_relative_strength`, `peer_rows` | 섹터 영향, 대장주 연동, peer 비교 |
| 미국 야간 전이 | 내부 계산 | `transmission_beta`, `transmission_corr`, `overnight_signal`, `volatility_spillover_score` | 장전 미국 증시 영향 |
| 유사 이벤트 패턴 | 내부 계산 | `pattern_bias`, `pattern_confidence`, `avg_return_1d`, `avg_return_5d` | 이벤트 당일 변동성 주의, 유사 패턴 반영 |
| 문서 요약 | Gemini + fallback | `document_summaries`, `material_disclosures` | 이벤트 근거 문장 생성 |

### 5.2 데이터 처리 흐름
1. `AnalysisPipeline.run()`이 가격, 뉴스, 공시, 재무제표, 거시, 섹터 모멘텀, 미국 야간 전이 데이터를 수집한다.
2. `build_features()`가 정규화 feature를 만든다.
3. `evaluate_signal()`이 신호 점수, 품질 점수, 상승/하락 근거, 리스크 플래그를 계산한다.
4. `passes_quality_gate()`가 최소 품질 조건을 확인하고 미달 시 리스크 플래그를 추가한다.
5. `build_stock_decision()`이 영향 계층 점수, 기간별 점수, 최종 결론, 근거 리스트를 만든다.
6. `renderStockReport()`가 사용자 이해를 위한 파생 문장과 설명용 프록시 점수를 계산한다.

### 5.3 feature 계산식
`build_features()`
- `ma_20`, `ma_60`
  - 최근 20일, 60일 종가 평균
- `rsi_14`
  - 최근 14일 RSI
- `volatility_20d`
  - 최근 20일 종가 표준편차 / MA20
- `atr_14_pct`
  - ATR / 종가
- `return_1d`, `return_5d`, `return_20d`
  - 기간 수익률
- `gap_return_1d`
  - 당일 시가 / 전일 종가 - 1
- `rel_volume`
  - 최근 거래량 / 최근 20일 평균 거래량
- `turnover_value_zscore`
  - 거래대금 z-score
- 텍스트/공시 파생
  - `news_sentiment_7d`, `news_attention_score`, `text_keyword_density`
  - `disclosure_bullish_score`, `disclosure_bearish_score`, `disclosure_net_score`, `material_disclosure_severity`
  - `supply_contract_score`, `financing_risk_score`, `shareholder_return_score`, `governance_score`
- 거시 파생
  - `macro_pressure_score`, `macro_support_score`, `macro_global_score`
  - `macro_surprise_index`, `macro_surprise_abs_mean`, `macro_consensus_coverage`
- 섹터 파생
  - `sector_coupling_score`, `sector_fund_flow_score`, `sector_breadth_score`, `sector_leader_relative_strength`
- 재무 파생
  - `revenue_growth_yoy`, `operating_margin`, `net_margin`, `debt_ratio`, `current_ratio`, `operating_cashflow_margin`
- 이벤트 파생
  - `event_volatility_score`, `event_pattern_bias`, `event_pattern_confidence`
- 미국 야간 파생
  - `overnight_us_beta`, `overnight_us_correlation`, `overnight_us_index_return`, `overnight_us_signal`, `overnight_us_vol_spillover`

### 5.4 시그널 점수와 품질 점수
`evaluate_signal()`

#### 시그널 점수 주요 가점
- 추세/기술
  - `price_vs_ma20 > 0` -> +8
  - `ma_20 > ma_60` -> +10
  - `return_5d > 0` -> 최대 +8
  - `rsi_14 <= 30` -> +4
  - `rel_volume > 1.3` -> +6
  - `turnover_value_zscore > 1.0` -> +4
- 텍스트/이벤트
  - `news_sentiment_7d * 8`
  - `news_attention_score * 4`
  - `disclosure_impact_30d * 10`
  - `disclosure_bullish_score * 7`
  - `disclosure_net_score * 10`
  - `material_disclosure_severity * 4`
  - `supply_contract_score * 5`
- 섹터/거시
  - `overnight_us_signal * 60`
  - `sector_fund_flow_score * 6`
  - `max(sector_coupling_score - 0.5, 0) * 8`
  - `sector_breadth_score * 4`
  - `sector_leader_relative_strength * 10`
  - `macro_support_score * 3`
  - `macro_global_score * 2`
  - `macro_surprise_index * 4`
  - `event_pattern_bias * 20 * max(0.3, event_pattern_confidence)`
- 재무
  - 매출 성장률, 영업이익률, 순이익률, 유동비율, 영업현금흐름 마진 가점

#### 시그널 점수 주요 감점
- `return_5d < -0.05` -> -5
- `rsi_14 >= 75` -> -10
- `financing_risk_score * 9`
- `max(material_disclosure_severity - 0.7, 0) * 5`
- `max(-overnight_us_signal, 0) * 70`
- `max(macro_pressure_score, 0) * 7`
- `macro_surprise_abs_mean * 2.5`
- `max(event_volatility_score - 0.6, 0) * 15`
- `debt_ratio` 과다 구간 감점

#### 품질 점수 감점
- 시작값 `82`
- `volatility_20d > 0.08` -> -12
- `atr_14_pct > 0.06` -> -8
- `rel_volume < 0.5` -> -10
- `sector_fund_flow_score < 0.2` -> -4
- `sector_coupling_score < 0.35` -> -3
- `financing_risk_score >= 0.5` -> -8
- `disclosure_bearish_score >= 0.6` -> -7
- `material_disclosure_severity >= 0.75` -> -4
- `overnight_us_vol_spillover >= 0.35` -> -4
- `macro_surprise_abs_mean >= 0.8` -> -5
- `event_volatility_score >= 0.65` -> -8
- `text_keyword_density > 0.08` -> -4
- `debt_ratio`, `current_ratio` 악화 추가 감점

#### 시그널 유형 분류
- `score >= 80` -> `SWING_CANDIDATE`
- `score >= 60` -> `EVENT_MONITOR`
- `score >= 45` -> `NEUTRAL`
- 그 외 -> `RISK_WARNING`
- 사용자 노출 시에는 한글 라벨로 변환한다.

### 5.5 영향 계층 점수
`_component_scores()`
- 시장 영향 점수
  - `50 + macro_support_score*24 - max(0, macro_pressure_score)*26 + macro_global_score*12`
- 섹터 영향 점수
  - `50 + price_vs_ma20*55 + return_20d*28 + (rel_volume-1.0)*8 + sector_fund_flow_score*18 + (sector_coupling_score-0.5)*24 + sector_breadth_score*10 + sector_leader_relative_strength*20`
- 종목 고유 점수
  - `50 + revenue_growth_yoy*35 + operating_margin*45 + net_margin*25 - max(debt_ratio-1.0, 0)*12`
- 이벤트 영향 점수
  - `50 + news_sentiment_7d*15 + disclosure_impact_30d*20 + supply_contract_score*18 - financing_risk_score*20`
- 밸류에이션/자본효율 점수
  - `50 + operating_cashflow_margin*40 + (current_ratio-1.0)*8 + shareholder_return_score*12 + governance_score*8`

### 5.6 기간별 점수와 최종 결론
`_horizon_scores()`
- 단기
  - `event_score*0.35 + sector_score*0.25 + market_score*0.15 + (50 + return_5d*180)*0.15 + (50 + news_attention_score*25 - abs(gap_return_1d)*120)*0.10`
- 스윙
  - `sector_score*0.30 + event_score*0.20 + market_score*0.20 + stock_specific_score*0.15 + (50 + price_vs_ma20*150 + return_20d*80)*0.15`
- 중기
  - `stock_specific_score*0.35 + valuation_score*0.25 + market_score*0.20 + sector_score*0.10 + (50 + macro_global_score*15 + revenue_growth_yoy*30)*0.10`
- 최종 판단 점수
  - `confidence_score = mean(short_term_score, swing_score, midterm_score)`
- 결론 규칙
  - `confidence_score >= 70 and quality_score >= 60` -> `분할매수`
  - `confidence_score >= 60` -> `보유`
  - `confidence_score < 45` -> `비중축소`
  - 나머지 -> `관찰`
- 이벤트 당일 예외
  - `EVENT_DAY_VOLATILITY_MODE`이면 `분할매수`, `보유`도 `관찰`로 낮춘다.

### 5.7 리포트 섹션별 근거
#### 상단 핵심 결론
- 종목
  - `instrument_name`, `ticker` -> `종목명(ticker)`
- 한 줄 투자 판단
  - `${종목명}은 현재 ${conclusion} 관점이며, 상태는 ${state_label}`
- 현재 상태 라벨
  - `_state_label()`
  - 규칙
    - 이벤트 모드면 `변동성 주의`
    - `close > ma_20 > ma_60` 그리고 `rsi_14 < 72` -> `상승 추세`
    - `close < ma_20 < ma_60` -> `하락 추세`
    - `rsi_14 >= 75` -> `단기 과열`
    - 그 외 -> `중립 또는 박스권`
- 판단 확신도
  - `confidence_score`
- 판단 유효 기간
  - `stockValidityWindow()`
  - 단기 우세면 `1~3거래일`, 스윙 우세면 `1~3주`, 중기 우세면 `1~3개월`
- 주도 해석 기간
  - `dominantStockHorizon()`

#### 점수 구조 분해
- 요약 카드
  - 판단 점수 = `confidence_score`
  - 품질 점수 = `quality_score`
  - 시그널 점수 = `signal.score`
  - 문서 근거 수 = `recent_timeline.length`
- 세부 점수 바
  - `short_term_score`, `swing_score`, `midterm_score`
  - `market_score`, `sector_score`, `stock_specific_score`, `event_score`, `valuation_score`
- 웹 파생 프록시
  - 재무/실적 프록시
    - `50 + revenue_growth_yoy*35 + operating_margin*80 + operating_cashflow_margin*50 - max(debt_ratio-1,0)*12`
  - 밸류에이션 부담 프록시
    - `40 + max(return_20d,0)*120 + max(rsi_14-60,0)*1.5 - operating_margin*20`
  - 리스크 압력 프록시
    - `financing_risk_score*35 + macro_pressure_score*25 + event_volatility_score*20 + risk_flags_count*4`

#### 상승/하락 요인과 핵심 변수
- 상승 근거 Top 5
  - `_bullish_factors()`
  - 양(+)의 `signal.reasons` + `document_summaries`
- 하락 근거 Top 5
  - `_bearish_factors()`
  - 음(-)의 `signal.reasons` + `signal.risk_flags`
- 판단을 가장 많이 바꾼 변수 3개
  - `stockChangedVariables()`
  - 후보: 섹터 자금 유입, 공시 순효과, 재무 체력, 거시 압력, 가격 모멘텀
- 새롭게 추가된 핵심 근거
  - `recent_timeline` 앞 3건 제목과 이벤트 유형
- 약해진 근거
  - `bearish_factors + signal.risk_flags` 앞 4개
- 상충 신호
  - `stockConflictSignals()`
  - 추세 강세 vs 자금조달 리스크, 재무 양호 vs RSI 과열, 이벤트 당일 변동성 주의 등을 설명

#### 기간별 해석
- `stockPeriodNarratives()`
- 단기
  - RSI, 거래량, 뉴스/공시 이벤트 중심
- 스윙
  - 섹터 자금 유입, 20일 수익률 중심
- 중기
  - 매출 성장률, 영업이익률, 거시 압력 중심

#### 시장-섹터-종목 계층 분석
- `stockLayerNarratives()`
- 시장 영향 점수
  - 시장 체제가 종목에 주는 영향
- 섹터 영향 점수
  - 섹터 강도, 자금 흐름, 대장주 연동
- 종목 고유 점수
  - 재무, 실적, 공시, 회사 고유 이슈
- 이벤트 영향 점수
  - 뉴스/공시가 현재 가설을 얼마나 바꾸는지

#### 섹터 모멘텀과 peer 비교
- 섹터 모멘텀 요약
  - `_sector_momentum_summary()`
  - 섹터명, 대장주, 커플링 점수, 자금 유입, breadth, 대장주 대비 상대 강도
- peer 표
  - `_sector_peer_snapshot()`
  - `leader -> target -> peer` 우선순위와 `return_20d` 정렬
  - 컬럼: 구분, 종목명(ticker), 20일 수익률, 상대 거래량, 거래대금 Z-score

#### 가격/수급/기술 해석
- 현재 가격 위치
  - 종가, MA20, MA60, 가격 괴리율, 상대 거래량, RSI
- 변동성 / 경계 구간
  - `volatility_20d`, `atr_14_pct`, `intraday_range_pct`
- 기술 경고
  - `stockTechnicalWarnings()`
  - RSI 과열, 거래량 부족, 변동성 과다, 장중 변동폭 과다

#### 이벤트·뉴스·공시 해석
- 최근 이벤트 타임라인
  - `_timeline()`
  - `source`, `event_type`, `published_at`, `title`, `summary`
- 최근 공시 핵심 요약
  - `material_disclosures`
  - `event_label`, `net_score`, `bullish_score`, `bearish_score`, `event_severity`, `rationale`
- 최근 뉴스 핵심 요약
  - `splitDocumentSummaries()`로 `source == news`만 추출
- 이벤트 우선순위
  - `material_disclosures`의 `net_score`, `event_label`, `title`

#### 재무/실적/가치 판단
- 최근 실적 흐름
  - `_financial_summary()`
  - 매출 증가율, 영업이익률, 순이익률, 부채비율, 유동비율, 영업현금흐름 마진
- 이익 체력 / 재무 안정성
  - 재무 수치를 다시 본문에 명시
- 자금조달 / 주주환원 / 거버넌스
  - `financing_risk_score`, `shareholder_return_score`, `governance_score`, `valuationBurden`

#### 거시/정책 영향
- 중요 거시 변수
  - `stockMacroSensitivity()`
  - 섹터별 민감도 규칙을 사용
- 거시·정책 근거
  - `_macro_summary()`
  - 미국 야간 전이 우선 반영
  - `global_macro_pressure`에서 종목/섹터 관련성 점수 `>= 0.85`인 항목만 선택
- 유사 이벤트 패턴 요약
  - `_event_pattern_summary()`
  - 현재 이벤트 유형, 표본 수, 평균 1일/5일 반응, 패턴 신뢰도, 변동성 주의 모드

#### 체크포인트 및 반증 조건
- 체크포인트
  - `_change_triggers()`
  - 신규 공시, 거시 방향 전환, 거래대금 수반 돌파, 과열 해소, 자금조달 리스크 완화, 이벤트 후속 방향 확인
- 이 판단이 틀릴 수 있는 이유
  - `signal.risk_flags`
- 무효화 / 상향 / 하향 재평가 조건
  - `change_triggers[0]`, `bullish_factors[0]`, `bearish_factors[0]`
- 다음 확인 예정 이벤트
  - `recent_timeline` 앞 4건의 `event_type: title`

#### 데이터 신뢰 및 설명 가능성
- 사용 데이터 요약
  - 문서/공시/뉴스 건수
  - 공시 점수 데이터 건수
  - 응답 경로
  - 품질 점수
- 최신성
  - 생성 시각, freshnessLabel, 파이프라인 상태, 문서 근거 수
- 해석 제약
  - 밸류에이션 부담은 프록시
  - 시장/섹터 영향은 대표 종목 기반
  - 이벤트 해석은 문서 요약과 공시 점수화 결합

### 5.8 결과 리포트가 근거 없이 보이지 않도록 하는 원칙
- 결론 문장은 반드시 `conclusion`, `state_label`, `confidence_score`에서 나온다.
- 상승/하락 요인은 반드시 `signal.reasons`, `risk_flags`, `document_summaries`, `material_disclosures`에서 나온다.
- 기간별 문장은 반드시 기간 점수와 관련 feature를 바탕으로 생성한다.
- 거시/정책 문장은 반드시 종목 관련성 필터를 통과한 항목만 사용한다.
- 이벤트 섹션은 반드시 실제 타임라인 또는 공시 점수화 데이터만 사용한다.
- peer 비교는 반드시 `sector_momentum.peer_rows` 기반이다.

## 6. 다음 확장 범위
- 다음 문서화 단계는 `Action Planner`, `Watchlist Alerts`를 같은 수준으로 상세화하는 것이다.
- 현재 문서는 `Market Regime`, `Stock Decision` 두 제품을 우선적으로 상세 문서화한 상태다.
