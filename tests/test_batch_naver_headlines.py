from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import batch_ingestion
from app.main import app
from app.schemas.batch_ingestion import BatchIngestionResponse


def test_naver_headlines_batch_route(monkeypatch) -> None:
    def fake_ingest_naver_section_headlines(db, max_items=10):
        return BatchIngestionResponse(
            source_system='NAVER_HEADLINE_NEWS',
            request_id='batch-test',
            started_at_utc=datetime.now(timezone.utc),
            finished_at_utc=datetime.now(timezone.utc),
            fetched_count=max_items * 6,
            stored_count=max_items * 6,
            skipped_count=0,
            saved_call_dir='archive/test',
            message='Naver headline news batch completed',
        )

    monkeypatch.setattr(batch_ingestion.ingestor, 'ingest_naver_section_headlines', fake_ingest_naver_section_headlines)
    client = TestClient(app)
    response = client.post('/api/v1/batch/naver/headlines', json={'max_items': 10})

    assert response.status_code == 200
    assert response.json()['source_system'] == 'NAVER_HEADLINE_NEWS'
