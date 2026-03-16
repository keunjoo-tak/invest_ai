from datetime import date, datetime, timezone

from app.services.ingestion.providers import SourceProviderClient

UTC = timezone.utc


def test_fetch_macro_event_risk_derives_rows(monkeypatch) -> None:
    client = SourceProviderClient()

    monkeypatch.setattr(
        client,
        'fetch_official_event_stream',
        lambda as_of_date, horizon_days=30: [
            {
                'scheduled_at_utc': datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
                'title': 'FOMC Meeting',
                'event_code': 'FED_FOMC_2026-03-15',
            }
        ],
    )
    monkeypatch.setattr(
        client,
        'fetch_broad_issue_stream',
        lambda as_of_date, lookback_days=7: [
            {
                'title': 'Inflation fears rise again',
                'content_text': 'inflation risk is rising',
                'publish_time_utc': datetime(2026, 3, 12, 1, 0, tzinfo=UTC),
            }
        ],
    )

    rows = client._fetch_macro_event_risk(date(2026, 3, 12))
    names = {row['indicator_name'] for row in rows}
    assert 'UPCOMING_OFFICIAL_EVENT_RISK' in names
    assert 'BROAD_ISSUE_STREAM_TONE' in names
