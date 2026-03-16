from datetime import date, timedelta

from app.services.features.feature_builder import build_features
from app.services.ingestion.providers import InstrumentProfile, SourceProviderClient


def _make_us_series() -> list[tuple[date, float]]:
    base = date(2026, 3, 2)
    closes = [100.0, 102.0, 101.0, 104.0, 106.0, 105.0, 107.0, 109.0, 111.0, 110.0, 112.0, 115.0, 114.0, 116.0]
    return [(base + timedelta(days=idx), value) for idx, value in enumerate(closes)]


def _make_kr_prices(us_series: list[tuple[date, float]]) -> list[dict]:
    rows = []
    prev_close = 100.0
    for idx in range(1, len(us_series)):
        trade_date = us_series[idx][0] + timedelta(days=1)
        us_ret = (us_series[idx][1] / us_series[idx - 1][1]) - 1
        gap = us_ret * 0.8
        open_price = round(prev_close * (1 + gap), 2)
        close_price = round(open_price * 1.01, 2)
        rows.append({
            "trade_date": trade_date,
            "open": open_price,
            "high": round(close_price * 1.01, 2),
            "low": round(open_price * 0.99, 2),
            "close": close_price,
            "volume": 100000 + idx * 1000,
        })
        prev_close = close_price
    return rows


def test_fetch_us_overnight_transmission_estimates_positive_beta(monkeypatch) -> None:
    client = SourceProviderClient()
    client._response_cache.clear()
    us_series = _make_us_series()
    kr_prices = _make_kr_prices(us_series)

    monkeypatch.setattr(client, 'resolve_instrument', lambda ticker: InstrumentProfile(ticker='005930', name_kr='Samsung Electronics', sector='\ubc18\ub3c4\uccb4'))
    monkeypatch.setattr(client, '_fetch_fred_series_history', lambda series_id, as_of_date, lookback_days=180: us_series)
    monkeypatch.setattr(client, '_select_us_overnight_index', lambda sector: ('NASDAQCOM', 'NASDAQ Composite'))
    monkeypatch.setattr(client, 'fetch_price_daily', lambda ticker, as_of_date, lookback_days: kr_prices)
    monkeypatch.setattr(client, '_is_korea_premarket', lambda as_of_date: True)

    out = client.fetch_us_overnight_transmission('005930', kr_prices[-1]['trade_date'], 120)

    assert out['applied'] is True
    assert out['reference_index'] == 'NASDAQCOM'
    assert out['sample_size'] >= 5
    assert out['transmission_beta'] > 0.5
    assert out['overnight_signal'] != 0.0


def test_build_features_ignores_overnight_signal_when_not_applied() -> None:
    prices = [
        {
            "trade_date": date(2026, 3, min(idx + 1, 28)),
            "open": 100 + idx,
            "high": 101 + idx,
            "low": 99 + idx,
            "close": 100 + idx,
            "volume": 100000 + idx * 1000,
        }
        for idx in range(40)
    ]
    features = build_features(
        date(2026, 3, 14),
        prices,
        [],
        [],
        [],
        financials={},
        sector_momentum={},
        overnight_transmission={
            "applied": False,
            "transmission_beta": 0.9,
            "transmission_corr": 0.8,
            "latest_us_return": -0.02,
            "overnight_signal": -0.015,
            "volatility_spillover_score": 0.4,
        },
    )

    assert features.overnight_us_beta == 0.0
    assert features.overnight_us_signal == 0.0
    assert features.overnight_us_vol_spillover == 0.0


def test_select_us_overnight_index_by_sector() -> None:
    client = SourceProviderClient()
    assert client._select_us_overnight_index('\ubc18\ub3c4\uccb4') == ('NASDAQCOM', 'NASDAQ Composite')
    assert client._select_us_overnight_index('\uc99d\uad8c') == ('DJIA', 'Dow Jones Industrial Average')
    assert client._select_us_overnight_index('\uc804\ub825\u00b7\uc5d0\ub108\uc9c0') == ('SP500', 'S&P 500')


def test_confirmed_us_previous_close_required() -> None:
    client = SourceProviderClient()
    assert client._has_confirmed_us_previous_close(date(2026, 3, 16), '2026-03-14') is True
    assert client._has_confirmed_us_previous_close(date(2026, 3, 14), '2026-03-14') is False
    assert client._has_confirmed_us_previous_close(date(2026, 3, 20), '2026-03-14') is False
