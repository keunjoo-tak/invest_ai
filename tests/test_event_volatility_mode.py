from datetime import date, datetime, timedelta, timezone

from app.services.features.feature_builder import build_event_pattern_snapshot, build_features
from app.services.signal.scorer import evaluate_signal

UTC = timezone.utc


def _make_prices() -> list[dict]:
    base = date(2026, 2, 1)
    rows = []
    close = 100.0
    for idx in range(60):
        trade_date = base + timedelta(days=idx)
        open_price = close * (1 + (0.002 if idx % 7 else -0.001))
        close = open_price * (1 + (0.004 if idx % 9 else -0.003))
        rows.append(
            {
                'trade_date': trade_date,
                'open': round(open_price, 2),
                'high': round(close * 1.01, 2),
                'low': round(open_price * 0.99, 2),
                'close': round(close, 2),
                'volume': 100000 + (idx * 1500),
            }
        )
    return rows


def test_event_volatility_mode_is_enabled_for_material_event_day() -> None:
    as_of_date = date(2026, 3, 20)
    prices = _make_prices()
    disclosures = [
        {
            'title': '전환사채 발행 결정',
            'event_type': 'financing',
            'publish_time_utc': datetime(2026, 3, 20, 0, 30, tzinfo=UTC),
            'impact_score': 0.85,
            'material_disclosure_severity': 0.9,
        },
        {
            'title': '유상증자 결정',
            'event_type': 'financing',
            'publish_time_utc': datetime(2026, 3, 5, 1, 0, tzinfo=UTC),
            'impact_score': 0.7,
            'material_disclosure_severity': 0.8,
        },
        {
            'title': '신주인수권부사채 발행',
            'event_type': 'financing',
            'publish_time_utc': datetime(2026, 2, 20, 1, 0, tzinfo=UTC),
            'impact_score': 0.65,
            'material_disclosure_severity': 0.75,
        },
    ]

    snapshot = build_event_pattern_snapshot(as_of_date, prices, [], disclosures)
    assert snapshot['volatility_caution_mode'] is True
    assert snapshot['event_volatility_score'] >= 0.65

    features = build_features(as_of_date, prices, [], disclosures, [], event_pattern=snapshot)
    signal = evaluate_signal(features)

    assert features.event_volatility_score >= 0.65
    assert 'EVENT_DAY_VOLATILITY_MODE' in signal.risk_flags
