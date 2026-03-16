from datetime import date, datetime, timezone

from app.schemas.analysis import AlertPayload, AnalyzeTickerResponse
from app.schemas.common import MarketFeatureSet, SignalResult
from app.schemas.decision_products import MarketRegimeResponse
from app.services.ingestion.providers import SourceProviderClient
from app.services.intelligence.decision_products import DecisionProductService


def _analysis_fixture() -> AnalyzeTickerResponse:
    features = MarketFeatureSet(
        as_of_date=date(2026, 3, 15),
        close=100.0,
        ma_20=98.0,
        ma_60=95.0,
        rsi_14=55.0,
        volatility_20d=0.03,
        atr_14_pct=0.02,
        return_1d=0.01,
        return_5d=0.03,
        return_20d=0.08,
        gap_return_1d=0.0,
        price_vs_ma20=0.02,
        price_vs_ma60=0.05,
        rel_volume=1.2,
        turnover_value_zscore=0.8,
        intraday_range_pct=0.02,
        news_sentiment_7d=0.2,
        news_attention_score=0.3,
        text_keyword_density=0.02,
        disclosure_impact_30d=0.15,
        disclosure_bullish_score=0.25,
        disclosure_bearish_score=0.05,
        disclosure_net_score=0.20,
        material_disclosure_severity=0.30,
        supply_contract_score=0.1,
        financing_risk_score=0.05,
        shareholder_return_score=0.1,
        governance_score=0.1,
        earnings_event_ratio=0.1,
        contract_event_ratio=0.1,
        macro_pressure_score=0.2,
        macro_support_score=0.2,
        macro_global_score=0.1,
        revenue_growth_yoy=0.1,
        operating_margin=0.12,
        net_margin=0.1,
        debt_ratio=0.5,
        current_ratio=1.5,
        operating_cashflow_margin=0.11,
        sector_coupling_score=0.6,
        sector_fund_flow_score=0.7,
        sector_breadth_score=0.65,
        sector_leader_relative_strength=0.08,
    )
    signal = SignalResult(signal_type='EVENT_MONITOR', direction='OBSERVE', score=65.0, quality_score=70.0)
    return AnalyzeTickerResponse(
        request_id='relevance-test',
        ticker='005930',
        instrument_name='삼성전자',
        as_of_date=date(2026, 3, 15),
        generated_at_utc=datetime.now(timezone.utc),
        response_language='ko',
        features=features,
        signal=signal,
        explanation={
            'sector_momentum': {'sector': '반도체'},
            'overnight_transmission': {},
            'document_summaries': [],
        },
        alert=AlertPayload(should_send=False, message='preview'),
    )


def test_instrument_news_filter_keeps_only_stock_relevant_items() -> None:
    client = SourceProviderClient()
    profile = client.resolve_instrument('005930')
    rows = [
        {
            'title': 'Samsung Electronics earnings recovery expected',
            'content_text': 'HBM shipments and profit outlook are improving for Samsung Electronics.',
            'url': 'https://example.com/relevant',
            'publish_time_utc': datetime.now(timezone.utc),
        },
        {
            'title': 'Middle East risk pushes Kospi lower',
            'content_text': 'This is a broad market article without any company-specific catalyst.',
            'url': 'https://example.com/irrelevant',
            'publish_time_utc': datetime.now(timezone.utc),
        },
    ]

    filtered = client._filter_relevant_instrument_news(profile, rows)

    assert len(filtered) == 1
    assert filtered[0]['url'] == 'https://example.com/relevant'
    assert filtered[0]['stock_relevance_score'] >= 0.62


def test_macro_summary_prefers_sector_relevant_rows() -> None:
    service = DecisionProductService()
    analysis = _analysis_fixture()
    regime = MarketRegimeResponse(
        as_of_date=date(2026, 3, 15),
        generated_at_utc=datetime.now(timezone.utc),
        regime='위험선호',
        regime_score=72.0,
        market_one_line='시장 위험선호가 유지되고 있습니다.',
        global_macro_pressure=[
            {'indicator_name': 'KR_EXPORT_SEARCH', 'surprise_index': 0.8, 'surprise_confidence': 0.3, 'country': 'KR'},
            {'indicator_name': 'SECTOR_SEMICONDUCTOR_NEWS', 'surprise_index': 0.6, 'surprise_confidence': 0.3, 'country': 'GLOBAL'},
            {'indicator_name': 'US_CPI_INDEX', 'surprise_index': 0.7, 'surprise_confidence': 0.3, 'country': 'US'},
        ],
        strong_sectors=[],
        weak_sectors=[],
        strategy_hints=[],
        representative_symbols=[],
        pipeline_status={},
    )

    summary = service._macro_summary(regime, analysis)

    assert any('KR_EXPORT_SEARCH' in item for item in summary)
    assert any('SECTOR_SEMICONDUCTOR_NEWS' in item for item in summary)
    assert all('US_CPI_INDEX' not in item for item in summary)
