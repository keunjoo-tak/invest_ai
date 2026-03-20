from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import scheduler_control
from app.core.config import get_settings
from app.main import app
from app.schemas.batch_ingestion import BatchIngestionResponse


def _set_scheduler_secret(monkeypatch) -> None:
    monkeypatch.setenv('SCHEDULER_SHARED_SECRET', 'test-secret')
    get_settings.cache_clear()


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_scheduler_trigger_requires_secret(monkeypatch) -> None:
    _set_scheduler_secret(monkeypatch)
    try:
        client = TestClient(app)
        response = client.post('/api/v1/internal/scheduler/jobs/market_regime_snapshot', json={})
        assert response.status_code == 401
    finally:
        _reset_settings()


def test_scheduler_trigger_runs_job(monkeypatch) -> None:
    _set_scheduler_secret(monkeypatch)

    def fake_run_scheduler_job(job_id, db, max_items_override=None):
        assert job_id == 'market_regime_snapshot'
        assert max_items_override == 3
        return BatchIngestionResponse(
            source_system='MARKET_REGIME_SNAPSHOT',
            request_id='scheduler-test',
            started_at_utc=datetime.now(timezone.utc),
            finished_at_utc=datetime.now(timezone.utc),
            fetched_count=1,
            stored_count=1,
            skipped_count=0,
            saved_call_dir='downloads/test',
            message='ok',
        )

    monkeypatch.setattr(scheduler_control, 'run_scheduler_job', fake_run_scheduler_job)
    try:
        client = TestClient(app)
        response = client.post(
            '/api/v1/internal/scheduler/jobs/market_regime_snapshot',
            json={'max_items': 3},
            headers={'X-InvestAI-Scheduler-Key': 'test-secret'},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload['job_id'] == 'market_regime_snapshot'
        assert payload['result']['source_system'] == 'MARKET_REGIME_SNAPSHOT'
    finally:
        _reset_settings()
