from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ExternalDocument
from app.schemas.analysis import AlertPayload, AnalyzeTickerResponse
from app.schemas.common import MarketFeatureSet, SignalResult
from app.services.intelligence import market_pulse
from app.services.intelligence.decision_products import DecisionProductService
from app.services.intelligence.market_pulse import MarketPulseEngine
from app.services.ingestion.research_normalizer import normalize_research_document

UTC = timezone.utc


def _analysis_fixture() -> AnalyzeTickerResponse:
    features = MarketFeatureSet(
        as_of_date=date(2026, 3, 18),
        close=100.0,
        ma_20=97.0,
        ma_60=92.0,
        rsi_14=56.0,
        volatility_20d=0.03,
        atr_14_pct=0.02,
        return_1d=0.01,
        return_5d=0.03,
        return_20d=0.07,
        gap_return_1d=0.0,
        price_vs_ma20=0.03,
        price_vs_ma60=0.08,
        rel_volume=1.1,
        turnover_value_zscore=0.6,
        intraday_range_pct=0.02,
        news_sentiment_7d=0.1,
        news_attention_score=0.2,
        text_keyword_density=0.02,
        disclosure_impact_30d=0.1,
        disclosure_bullish_score=0.1,
        disclosure_bearish_score=0.02,
        disclosure_net_score=0.08,
        material_disclosure_severity=0.12,
        supply_contract_score=0.08,
        financing_risk_score=0.02,
        shareholder_return_score=0.05,
        governance_score=0.05,
        earnings_event_ratio=0.1,
        contract_event_ratio=0.1,
        macro_pressure_score=0.15,
        macro_support_score=0.2,
        macro_global_score=0.1,
        revenue_growth_yoy=0.1,
        operating_margin=0.12,
        net_margin=0.1,
        debt_ratio=0.6,
        current_ratio=1.4,
        operating_cashflow_margin=0.12,
    )
    return AnalyzeTickerResponse(
        request_id='research-test',
        ticker='005930',
        instrument_name='삼성전자',
        as_of_date=date(2026, 3, 18),
        generated_at_utc=datetime.now(UTC),
        response_language='ko',
        features=features,
        signal=SignalResult(signal_type='EVENT_MONITOR', direction='OBSERVE', score=62.0, quality_score=70.0),
        explanation={'sector_momentum': {'sector': '반도체'}},
        alert=AlertPayload(should_send=False, message='preview'),
    )


def _price_rows(start_price: float) -> list[dict]:
    rows = []
    d0 = date(2026, 2, 10)
    price = start_price
    for i in range(40):
        trade_date = d0 + timedelta(days=i)
        if trade_date.weekday() >= 5:
            continue
        price *= 1.01
        rows.append({'trade_date': trade_date, 'close': round(price, 2)})
    return rows


def test_research_normalizer_extracts_company_signal() -> None:
    normalized = normalize_research_document(
        house_name='삼성증권',
        source_id='S41',
        access_tier='PUBLIC_OPEN',
        redistribution_policy='DERIVED_ONLY',
        layout_profile='samsung_sec_research',
        market_scope='KR',
        title='005930 target price upgrade report',
        content_text='Maintain buy on 005930 and set target price 120000. HBM demand and earnings recovery are improving.',
        url='https://example.com/report',
        published_at_utc=datetime(2026, 3, 18, 0, 0, tzinfo=UTC),
        summary={'summary': 'HBM 수요 확대와 실적 개선 가능성을 함께 설명합니다.', 'key_points': ['HBM 수요 확대']},
        prediction_signal={'primary_event': 'earnings'},
        house_quality_score=0.85,
    )

    assert normalized['report_scope'] == 'company'
    assert 'stock_decision' in normalized['service_targets']
    assert normalized['primary_ticker'] == '005930'
    assert normalized['research_scores']['company_recommendation_score'] > 0


def test_market_regime_and_stock_decision_use_public_research_docs(monkeypatch) -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    target_date = date(2026, 3, 18)

    monkeypatch.setattr(market_pulse, 'SessionLocal', SessionLocal)

    pulse = MarketPulseEngine()
    monkeypatch.setattr(pulse.providers, '_fallback_catalog', lambda: [{'ticker': '005930'}, {'ticker': '000660'}])
    monkeypatch.setattr(pulse.providers, 'fetch_price_daily', lambda ticker, as_of_date, lookback_days: _price_rows(100 if ticker == '005930' else 110))
    monkeypatch.setattr(pulse.providers, 'fetch_macro', lambda as_of_date: [])
    monkeypatch.setattr(pulse.providers, 'resolve_instrument', lambda ticker: SimpleNamespace(name_kr='삼성전자' if ticker == '005930' else 'SK하이닉스'))

    with SessionLocal() as db:
        db.add(ExternalDocument(
            source_system='PUBLIC_RESEARCH_REPORTS',
            source_id='S41',
            source_doc_id='research-market-1',
            category='daily_strategy',
            title='시장 위험선호 회복 전망',
            url='https://example.com/market-research',
            publish_time_utc=datetime(2026, 3, 18, 1, 0, tzinfo=UTC),
            ticker=None,
            instrument_name=None,
            sector=None,
            event_type='research_report',
            content_text='시장 위험선호 회복이 국내 증시에 우호적으로 작용할 수 있습니다.',
            summary_json={'summary': '시장 위험선호 회복이 국내 증시에 우호적이라는 내용입니다.'},
            metadata_json={
                'house_name': '삼성증권',
                'report_type': 'daily_strategy',
                'service_targets': ['market_regime'],
                'stance': 'positive',
                'feature_confidence': 0.82,
                'research_scores': {
                    'freshness_score': 0.9,
                    'house_quality_score': 0.86,
                    'risk_on_off_score': 0.55,
                    'policy_risk_score': 0.05,
                    'geopolitical_risk_score': 0.0,
                },
            },
            local_doc_dir='archive/test',
            fingerprint='fp-research-market-1',
        ))
        db.add(ExternalDocument(
            source_system='PUBLIC_RESEARCH_REPORTS',
            source_id='S41',
            source_doc_id='research-stock-1',
            category='company_report',
            title='삼성전자 목표주가 상향',
            url='https://example.com/stock-research',
            publish_time_utc=datetime(2026, 3, 18, 2, 0, tzinfo=UTC),
            ticker='005930',
            instrument_name='삼성전자',
            sector='반도체',
            event_type='research_report',
            content_text='삼성전자 실적 개선 가능성을 설명합니다.',
            summary_json={'summary': 'HBM 수요 확대로 삼성전자 실적 개선 가능성이 높아졌다는 내용입니다.'},
            metadata_json={
                'house_name': '삼성증권',
                'report_type': 'company_report',
                'service_targets': ['stock_decision', 'action_planner'],
                'stance': 'positive',
                'feature_confidence': 0.88,
                'ticker_tags': ['005930'],
                'company_tags': ['삼성전자'],
                'sector_tags': ['반도체'],
                'price_upside_pct': 15.0,
                'catalyst_bullets': ['HBM 수요 확대 지속'],
                'research_scores': {
                    'freshness_score': 0.92,
                    'house_quality_score': 0.86,
                    'company_recommendation_score': 0.7,
                    'target_price_revision_score': 0.12,
                    'thesis_positive_score': 0.82,
                    'thesis_negative_score': 0.12,
                    'industry_tailwind_score': 0.68,
                    'industry_headwind_score': 0.15,
                    'catalyst_near_term_score': 0.7,
                },
            },
            local_doc_dir='archive/test',
            fingerprint='fp-research-stock-1',
        ))
        db.commit()

        overview = pulse.overview(target_date)
        service = DecisionProductService()
        consensus, bulls, bears, checkpoints, evidence_docs = service._load_research_consensus(db, _analysis_fixture())

    assert overview.research_briefs
    assert overview.research_briefs[0]['house_name'] == '삼성증권'
    assert consensus['matched_doc_count'] == 1
    assert consensus['recommendation_score'] > 0
    assert bulls
    assert checkpoints
    assert evidence_docs[0]['title'] == '삼성전자 목표주가 상향'


def test_market_regime_filters_out_technical_research_notes(monkeypatch) -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    target_date = date(2026, 3, 18)

    monkeypatch.setattr(market_pulse, 'SessionLocal', SessionLocal)

    pulse = MarketPulseEngine()
    monkeypatch.setattr(pulse.providers, '_fallback_catalog', lambda: [{'ticker': '005930'}, {'ticker': '000660'}])
    monkeypatch.setattr(pulse.providers, 'fetch_price_daily', lambda ticker, as_of_date, lookback_days: _price_rows(100 if ticker == '005930' else 110))
    monkeypatch.setattr(pulse.providers, 'fetch_macro', lambda as_of_date: [])
    monkeypatch.setattr(pulse.providers, 'resolve_instrument', lambda ticker: SimpleNamespace(name_kr='????' if ticker == '005930' else 'SK????'))

    with SessionLocal() as db:
        db.add(ExternalDocument(
            source_system='PUBLIC_RESEARCH_REPORTS',
            source_id='S41',
            source_doc_id='research-market-filter-1',
            category='daily_strategy',
            title='?? ?? ?? ??',
            url='https://example.com/market-filter-1',
            publish_time_utc=datetime(2026, 3, 18, 1, 0, tzinfo=UTC),
            ticker=None,
            instrument_name=None,
            sector=None,
            event_type='research_report',
            content_text='??? ??? ?? ?? ??? ?? ??? ?????? ?? ??????.',
            summary_json={'summary': '??? ??? ?? ??? ?? ??? ?????? ?? ?? ?????.'},
            metadata_json={
                'house_name': '????',
                'report_type': 'daily_strategy',
                'report_scope': 'market',
                'service_targets': ['market_regime'],
                'stance': 'positive',
                'feature_confidence': 0.82,
                'research_scores': {
                    'freshness_score': 0.9,
                    'house_quality_score': 0.86,
                    'risk_on_off_score': 0.55,
                    'policy_risk_score': 0.05,
                    'geopolitical_risk_score': 0.0,
                    'actionability_score': 0.7,
                },
            },
            local_doc_dir='archive/test',
            fingerprint='fp-research-market-filter-1',
        ))
        db.add(ExternalDocument(
            source_system='PUBLIC_RESEARCH_REPORTS',
            source_id='S41',
            source_doc_id='research-market-filter-2',
            category='macro',
            title='Attention/Transformer Architecture Note',
            url='https://example.com/market-filter-2',
            publish_time_utc=datetime(2026, 3, 18, 2, 0, tzinfo=UTC),
            ticker=None,
            instrument_name=None,
            sector=None,
            event_type='research_report',
            content_text='This note explains transformer embedding, residual connection, and layer normalization architecture.',
            summary_json={'summary': 'Attention/Transformer architecture with embedding and residual connection explanation.'},
            metadata_json={
                'house_name': '????',
                'report_type': 'macro',
                'report_scope': 'market',
                'service_targets': ['market_regime'],
                'stance': 'neutral',
                'feature_confidence': 0.9,
                'research_scores': {
                    'freshness_score': 0.88,
                    'house_quality_score': 0.86,
                    'risk_on_off_score': 0.0,
                    'policy_risk_score': 0.0,
                    'geopolitical_risk_score': 0.0,
                    'actionability_score': 0.2,
                },
            },
            local_doc_dir='archive/test',
            fingerprint='fp-research-market-filter-2',
        ))
        db.commit()

        overview = pulse.overview(target_date)

    assert len(overview.research_briefs) == 1
    assert overview.research_briefs[0]['report_type'] == 'daily_strategy'
    assert overview.research_briefs[0]['relevance_score'] >= 0.45
    assert all('Transformer' not in item['summary'] for item in overview.research_briefs)
