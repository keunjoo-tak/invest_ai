from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import batch_ingestion
from app.main import app
from app.schemas.batch_ingestion import BatchIngestionResponse


def test_market_regime_snapshot_batch_route(monkeypatch) -> None:
    def fake_ingest_market_regime_snapshot(db, max_items=1):
        return BatchIngestionResponse(
            source_system='MARKET_REGIME_SNAPSHOT',
            request_id='batch-test',
            started_at_utc=datetime.now(timezone.utc),
            finished_at_utc=datetime.now(timezone.utc),
            fetched_count=max_items,
            stored_count=1,
            skipped_count=0,
            saved_call_dir='archive/test',
            message='Market regime snapshot batch completed',
        )

    monkeypatch.setattr(batch_ingestion.ingestor, 'ingest_market_regime_snapshot', fake_ingest_market_regime_snapshot)
    client = TestClient(app)
    response = client.post('/api/v1/batch/market-regime-snapshot', json={'max_items': 1})

    assert response.status_code == 200
    assert response.json()['source_system'] == 'MARKET_REGIME_SNAPSHOT'
