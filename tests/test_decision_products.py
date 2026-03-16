from datetime import date, datetime, timezone

from app.schemas.analysis import AlertPayload, AnalyzeTickerResponse
from app.schemas.common import MarketFeatureSet, SignalResult
from app.services.intelligence.decision_products import DecisionProductService


def _analysis_fixture() -> AnalyzeTickerResponse:
    features = MarketFeatureSet(
        as_of_date=date.today(),
        close=110.0,
        ma_20=104.0,
        ma_60=98.0,
        rsi_14=58.0,
        volatility_20d=0.03,
        atr_14_pct=0.024,
        return_1d=0.01,
        return_5d=0.035,
        return_20d=0.11,
        gap_return_1d=0.003,
        price_vs_ma20=0.057,
        price_vs_ma60=0.122,
        rel_volume=1.4,
        turnover_value_zscore=1.2,
        intraday_range_pct=0.021,
        news_sentiment_7d=0.35,
        news_attention_score=0.45,
        text_keyword_density=0.03,
        disclosure_impact_30d=0.4,
        supply_contract_score=0.5,
        financing_risk_score=0.1,
        shareholder_return_score=0.2,
        governance_score=0.15,
        earnings_event_ratio=0.2,
        contract_event_ratio=0.3,
        macro_pressure_score=0.1,
        macro_support_score=0.25,
        macro_global_score=0.12,
        revenue_growth_yoy=0.16,
        operating_margin=0.14,
        net_margin=0.11,
        debt_ratio=0.7,
        current_ratio=1.6,
        operating_cashflow_margin=0.13,
    )
    signal = SignalResult(signal_type='EVENT_MONITOR', direction='OBSERVE', score=68.0, quality_score=74.0)
    return AnalyzeTickerResponse(
        request_id='test',
        ticker='005930',
        instrument_name='삼성전자',
        as_of_date=date.today(),
        generated_at_utc=datetime.now(timezone.utc),
        response_language='ko',
        features=features,
        signal=signal,
        explanation={
            'document_summaries': [
                {'source': '뉴스', 'title': '수요 개선 신호', 'summary': '핵심 전방 시장의 수요가 개선되고 있습니다.'},
                {'source': '공시', 'title': '공급 계약 체결', 'summary': '신규 공급 계약으로 매출 가시성이 높아졌습니다.'},
            ]
        },
        alert=AlertPayload(should_send=False, message='preview'),
    )


def test_component_scores_and_horizon_scores_are_bounded() -> None:
    service = DecisionProductService()
    analysis = _analysis_fixture()
    components = service._component_scores(analysis)
    horizons = service._horizon_scores(analysis, components)

    assert set(components) == {'market_score', 'sector_score', 'stock_specific_score', 'event_score', 'valuation_score'}
    assert set(horizons) == {'short_term_score', 'swing_score', 'midterm_score'}
    assert all(0.0 <= value <= 100.0 for value in components.values())
    assert all(0.0 <= value <= 100.0 for value in horizons.values())


def test_stock_decision_helpers_extract_explanatory_lists() -> None:
    service = DecisionProductService()
    analysis = _analysis_fixture()

    bullish = service._bullish_factors(analysis)
    bearish = service._bearish_factors(analysis)
    timeline = service._timeline(analysis)
    triggers = service._change_triggers(analysis)
    financial_summary = service._financial_summary(analysis)

    assert bullish
    assert isinstance(bearish, list)
    assert len(timeline) == 2
    assert triggers
    assert any('매출 증가율' in item for item in financial_summary)
