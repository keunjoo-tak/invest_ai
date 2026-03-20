from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import batch_ingestion
from app.main import app
from app.schemas.batch_ingestion import BatchIngestionResponse


def test_public_research_batch_route(monkeypatch) -> None:
    def fake_ingest_public_research_reports(db, max_items=10, group='all'):
        return BatchIngestionResponse(
            source_system='PUBLIC_RESEARCH_REPORTS',
            request_id='research-batch-test',
            started_at_utc=datetime.now(timezone.utc),
            finished_at_utc=datetime.now(timezone.utc),
            fetched_count=max_items,
            stored_count=3,
            skipped_count=1,
            saved_call_dir='archive/research',
            message=f'공개 리서치 배치 테스트 ({group})',
        )

    monkeypatch.setattr(batch_ingestion.ingestor, 'ingest_public_research_reports', fake_ingest_public_research_reports)
    client = TestClient(app)
    response = client.post('/api/v1/batch/research/public-reports', json={'max_items': 5, 'group': 'global'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['source_system'] == 'PUBLIC_RESEARCH_REPORTS'
    assert payload['stored_count'] == 3
