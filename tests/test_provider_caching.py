from datetime import date

from app.services.ingestion.providers import SourceProviderClient


def test_fetch_price_daily_uses_cache(monkeypatch) -> None:
    SourceProviderClient._response_cache.clear()
    client = SourceProviderClient()
    calls = {'count': 0}

    def fake_fetch_price_daily_kis(ticker: str, as_of_date: date, lookback_days: int):
        calls['count'] += 1
        return [{'trade_date': as_of_date, 'open': 1.0, 'high': 1.0, 'low': 1.0, 'close': 1.0, 'volume': 1}]

    monkeypatch.setattr(client, '_fetch_price_daily_kis', fake_fetch_price_daily_kis)

    first = client.fetch_price_daily('005930', date(2026, 3, 13), 60)
    second = client.fetch_price_daily('005930', date(2026, 3, 13), 60)

    assert calls['count'] == 1
    assert first == second


def test_fetch_macro_uses_cache(monkeypatch) -> None:
    SourceProviderClient._response_cache.clear()
    client = SourceProviderClient()
    calls = {'count': 0}

    def fake_macro_rows(as_of_date: date):
        calls['count'] += 1
        return [{'as_of_date': as_of_date, 'country': 'KR', 'indicator_name': 'TEST_MACRO', 'actual': 1.0, 'consensus': 0.0, 'surprise_std': 0.0, 'directional_interpretation': 'neutral'}]

    monkeypatch.setattr(client, '_fetch_macro_bok', fake_macro_rows)
    monkeypatch.setattr(client, '_fetch_macro_kosis', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_fred', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_bls', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_bea', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_fiscaldata', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_oecd', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_world_bank', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_imf', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_eurostat', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_newsapi', lambda as_of_date: [])
    monkeypatch.setattr(client, '_fetch_macro_event_risk', lambda as_of_date: [])

    first = client.fetch_macro(date(2026, 3, 13))
    second = client.fetch_macro(date(2026, 3, 13))

    assert calls['count'] == 1
    assert first == second
