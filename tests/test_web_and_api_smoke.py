from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import decision_products
from app.main import app
from app.schemas.analysis import AlertPayload, AnalyzeTickerResponse
from app.schemas.common import MarketFeatureSet, SignalResult
from app.schemas.decision_products import (
    ActionPlannerResponse,
    ActionScenario,
    MarketRegimeResponse,
    StockDecisionResponse,
    WatchlistAlertResponse,
    WatchlistSubscriptionDeleteResponse,
    WatchlistSubscriptionResponse,
)


def _analysis() -> AnalyzeTickerResponse:
    features = MarketFeatureSet(
        as_of_date=date(2026, 3, 13),
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
        macro_pressure_score=0.1,
        macro_support_score=0.2,
        macro_global_score=0.1,
        revenue_growth_yoy=0.1,
        operating_margin=0.12,
        net_margin=0.1,
        debt_ratio=0.5,
        current_ratio=1.5,
        operating_cashflow_margin=0.11,
    )
    signal = SignalResult(signal_type='EVENT_MONITOR', direction='OBSERVE', score=65.0, quality_score=70.0)
    return AnalyzeTickerResponse(
        request_id='smoke',
        ticker='005930',
        instrument_name='삼성전자',
        as_of_date=date(2026, 3, 13),
        generated_at_utc=datetime.now(timezone.utc),
        response_language='ko',
        features=features,
        signal=signal,
        explanation={
            'document_summaries': [
                {
                    'source': '뉴스',
                    'event_type': '뉴스',
                    'published_at': '2026-03-13T00:00:00Z',
                    'title': '반도체 수요 개선',
                    'summary': '메모리 수요 개선 기대가 반영되고 있습니다.',
                }
            ]
        },
        alert=AlertPayload(should_send=False, message='preview'),
    )


def _stock_decision() -> StockDecisionResponse:
    return StockDecisionResponse(
        ticker='005930',
        instrument_name='삼성전자',
        as_of_date=date(2026, 3, 13),
        generated_at_utc=datetime.now(timezone.utc),
        market_regime='위험선호',
        conclusion='보유',
        state_label='상승 추세',
        confidence_score=68.0,
        quality_score=72.0,
        short_term_score=64.0,
        swing_score=69.0,
        midterm_score=71.0,
        market_score=60.0,
        sector_score=63.0,
        stock_specific_score=66.0,
        event_score=61.0,
        valuation_score=62.0,
        bullish_factors=['수요 개선 기대'],
        bearish_factors=['단기 변동성 확대 가능성'],
        change_triggers=['신규 공시 확인'],
        recent_timeline=[{'source': '뉴스', 'event_type': '뉴스', 'published_at': '2026-03-13T00:00:00Z', 'title': '반도체 수요 개선', 'summary': '메모리 수요 개선 기대가 반영되고 있습니다.'}],
        sector_relative_strength=5.2,
        financial_summary=['매출 증가율 10.0%', '영업이익률 12.0%'],
        policy_macro_summary=['현재 시장 체제는 위험선호입니다.'],
        source_analysis=_analysis(),
        pipeline_status={'response_source': 'memory_cache', 'note': '캐시 응답'},
    )


def test_web_and_decision_api_smoke(monkeypatch) -> None:
    async def fake_market_regime(as_of_date=None, db=None):
        return MarketRegimeResponse(
            as_of_date=date(2026, 3, 13),
            generated_at_utc=datetime.now(timezone.utc),
            regime='위험선호',
            regime_score=7.5,
            market_one_line='현재 시장은 위험선호 구간입니다.',
            global_macro_pressure=[],
            strong_sectors=[{'sector': '반도체', 'score': 75.0}],
            weak_sectors=[{'sector': '필수소비재', 'score': 30.0}],
            strategy_hints=['강한 섹터의 주도주 중심으로 대응합니다.'],
            representative_symbols=[{'ticker': '005930', 'ret20_pct': 8.2}],
            pipeline_status={'response_source': 'batch_snapshot', 'snapshot_ready': True},
        )

    async def fake_stock_decision(db, ticker_or_name, as_of_date=None, lookback_days=365):
        return _stock_decision()

    async def fake_action_plan(db, req):
        return ActionPlannerResponse(
            ticker='005930',
            instrument_name='삼성전자',
            as_of_date=date(2026, 3, 13),
            generated_at_utc=datetime.now(timezone.utc),
            recommended_action='관찰 유지',
            action_reason='추가 확인이 필요한 구간입니다.',
            investment_horizon=req.investment_horizon,
            risk_profile=req.risk_profile,
            objective=req.objective,
            has_position=req.has_position,
            avg_buy_price=req.avg_buy_price,
            action_score=58.0,
            plan_validity_window='1~3주',
            preconditions=['시장 체제 유지 확인'],
            buy_interest_zone='98000 ~ 101000',
            invalidation_zone='94000 하회',
            target_zone='108000 ~ 112000',
            holding_plan='보유 중이면 무효화 구간 이탈 전까지 관찰합니다.',
            no_position_plan='미보유자는 추격 매수보다 조정 구간을 기다립니다.',
            scenarios=[ActionScenario(scenario='기본', trigger='거래대금 유지', expected_path='완만한 상승', action='분할 접근')],
            source_decision=_stock_decision(),
            pipeline_status={'response_source': 'derived_from_stock_decision'},
        )

    async def fake_watchlist_alert(db, req):
        return WatchlistAlertResponse(
            ticker='005930',
            instrument_name='삼성전자',
            as_of_date=date(2026, 3, 13),
            generated_at_utc=datetime.now(timezone.utc),
            should_alert_now=False,
            monitoring_state='관찰 유지',
            key_triggers=['신규 공시 확인'],
            risk_flags=['거시 불확실성'],
            catalyst_watchlist=['실적 발표'],
            alert_preview='즉시 대응 신호는 아니지만 관찰이 필요합니다.',
            source_signal=_analysis().signal,
            source_analysis=_analysis(),
            pipeline_status={'response_source': 'live_check'},
        )

    def fake_create_subscription(db, req):
        return WatchlistSubscriptionResponse(
            id=1,
            ticker='005930',
            instrument_name='삼성전자',
            channel='telegram',
            is_active=True,
            notes=req.notes,
            created_at_utc=datetime.now(timezone.utc),
            updated_at_utc=datetime.now(timezone.utc),
        )

    def fake_list_subscription(db):
        return [fake_create_subscription(db, type('Req', (), {'notes': '실적 점검'})())]

    def fake_delete_subscription(db, ticker_or_name, channel='telegram'):
        return WatchlistSubscriptionDeleteResponse(deleted=True, ticker='005930', channel=channel)

    monkeypatch.setattr(decision_products.service, 'build_market_regime', fake_market_regime)
    monkeypatch.setattr(decision_products.service, 'build_stock_decision', fake_stock_decision)
    monkeypatch.setattr(decision_products.service, 'build_action_plan', fake_action_plan)
    monkeypatch.setattr(decision_products.service, 'build_watchlist_alert', fake_watchlist_alert)
    monkeypatch.setattr(decision_products.service, 'add_watchlist_subscription', fake_create_subscription)
    monkeypatch.setattr(decision_products.service, 'list_watchlist_subscriptions', fake_list_subscription)
    monkeypatch.setattr(decision_products.service, 'delete_watchlist_subscription', fake_delete_subscription)

    client = TestClient(app)

    assert client.get('/app').status_code == 200
    assert client.get('/assets/app.js').status_code == 200
    assert client.get('/api/v1/health').status_code == 200
    assert client.get('/api/v1/market-regime/overview').status_code == 200
    assert client.get('/api/v1/stock-decision/005930').status_code == 200
    assert client.post('/api/v1/action-planner/analyze', json={'ticker_or_name': '005930', 'risk_profile': 'balanced', 'investment_horizon': 'swing', 'has_position': False}).status_code == 200
    assert client.post('/api/v1/watchlist-alerts/check', json={'ticker_or_name': '005930', 'notify': False, 'force_send': False}).status_code == 200
    assert client.post('/api/v1/watchlist-alerts/subscriptions', json={'ticker_or_name': '005930', 'channel': 'telegram', 'notes': '실적 점검'}).status_code == 200
    assert client.get('/api/v1/watchlist-alerts/subscriptions').status_code == 200
    assert client.delete('/api/v1/watchlist-alerts/subscriptions/005930?channel=telegram').status_code == 200
