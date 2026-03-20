from datetime import date, datetime, timedelta, timezone

from app.schemas.analysis import AlertPayload, AnalyzeTickerResponse
from app.schemas.common import MarketFeatureSet, SignalResult
from app.services.ingestion.providers import SourceProviderClient
from app.services.intelligence.decision_products import DecisionProductService


def _make_prices(start_close: float, daily_step: float, volume_base: int, volume_jump: int = 0) -> list[dict]:
    rows = []
    day = date(2026, 2, 1)
    close = start_close
    for idx in range(40):
        current_day = day + timedelta(days=idx)
        if current_day.weekday() >= 5:
            continue
        close += daily_step
        volume = volume_base + idx * 1000 + volume_jump
        rows.append(
            {
                "trade_date": current_day,
                "open": round(close - 0.5, 2),
                "high": round(close + 1.0, 2),
                "low": round(close - 1.0, 2),
                "close": round(close, 2),
                "volume": volume,
            }
        )
    return rows


def test_fetch_sector_momentum_calculates_coupling_and_flow(monkeypatch) -> None:
    client = SourceProviderClient()
    price_map = {
        '005930': _make_prices(70000, 220, 1_500_000, 300_000),
        '000660': _make_prices(120000, 360, 900_000, 250_000),
    }

    def fake_fetch_price_daily(ticker: str, as_of_date: date, lookback_days: int):
        return price_map[ticker]

    monkeypatch.setattr(client, 'fetch_price_daily', fake_fetch_price_daily)

    momentum = client.fetch_sector_momentum('000660', date(2026, 3, 14), 60)

    assert momentum['sector'] is not None
    assert momentum['leader_ticker'] == '005930'
    assert 0.0 <= momentum['sector_coupling_score'] <= 1.0
    assert momentum['sector_coupling_score'] > 0.5
    assert momentum['sector_fund_flow_score'] > 0.0
    assert momentum['sector_breadth_score'] > 0.0
    assert len(momentum['peer_rows']) >= 2
    assert momentum['peer_rows'][0]['ticker'] in {'005930', '000660'}


def test_sector_momentum_is_reflected_in_component_scores() -> None:
    service = DecisionProductService()
    analysis = AnalyzeTickerResponse(
        request_id='test',
        ticker='000660',
        instrument_name='SK하이닉스',
        as_of_date=date(2026, 3, 14),
        generated_at_utc=datetime(2026, 3, 14, tzinfo=timezone.utc),
        response_language='ko',
        features=MarketFeatureSet(
            as_of_date=date(2026, 3, 14),
            close=120.0,
            ma_20=115.0,
            ma_60=108.0,
            rsi_14=61.0,
            volatility_20d=0.03,
            atr_14_pct=0.02,
            return_1d=0.01,
            return_5d=0.03,
            return_20d=0.12,
            gap_return_1d=0.002,
            price_vs_ma20=0.043,
            price_vs_ma60=0.111,
            rel_volume=1.4,
            turnover_value_zscore=1.1,
            intraday_range_pct=0.021,
            news_sentiment_7d=0.2,
            news_attention_score=0.4,
            text_keyword_density=0.03,
            disclosure_impact_30d=0.3,
            supply_contract_score=0.1,
            financing_risk_score=0.0,
            shareholder_return_score=0.0,
            governance_score=0.0,
            earnings_event_ratio=0.0,
            contract_event_ratio=0.0,
            macro_pressure_score=0.1,
            macro_support_score=0.2,
            macro_global_score=0.1,
            macro_surprise_index=0.0,
            macro_surprise_abs_mean=0.0,
            macro_consensus_coverage=0.5,
            sector_coupling_score=0.82,
            sector_fund_flow_score=0.68,
            sector_breadth_score=1.0,
            sector_leader_relative_strength=0.04,
            revenue_growth_yoy=0.08,
            operating_margin=0.1,
            net_margin=0.08,
            debt_ratio=0.6,
            current_ratio=1.3,
            operating_cashflow_margin=0.1,
        ),
        signal=SignalResult(signal_type='EVENT_MONITOR', direction='OBSERVE', score=66.0, quality_score=72.0),
        explanation={},
        alert=AlertPayload(should_send=False, message='preview'),
    )

    components = service._component_scores(analysis)
    assert components['sector_score'] > 60
