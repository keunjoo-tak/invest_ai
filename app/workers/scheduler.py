from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.services.ingestion.batch_ingestor import BatchIngestor


def _run_policy_briefing_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_policy_briefing(db=db, max_items=40)
    finally:
        db.close()


def _run_bok_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_bok_publications(db=db, max_items=40)
    finally:
        db.close()


def _run_global_macro_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_global_macro_briefings(db=db, max_items=20)
    finally:
        db.close()


def _run_international_macro_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_international_macro_briefings(db=db, max_items=20)
    finally:
        db.close()


def _run_global_calendar_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_global_event_calendars(db=db, max_items=80)
    finally:
        db.close()


def _run_global_issue_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_global_issue_stream(db=db, max_items=40)
    finally:
        db.close()


def _run_naver_headline_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_naver_section_headlines(db=db, max_items=10)
    finally:
        db.close()


def _run_market_regime_snapshot_job() -> None:
    db = SessionLocal()
    try:
        BatchIngestor().ingest_market_regime_snapshot(db=db, max_items=1)
    finally:
        db.close()


def build_scheduler() -> BackgroundScheduler:
    """배치 스케줄러를 구성한다."""

    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_policy_briefing_job, 'cron', hour=6, minute=15, id='batch_policy_briefing', replace_existing=True)
    scheduler.add_job(_run_bok_job, 'cron', hour=6, minute=35, id='batch_bok_publications', replace_existing=True)
    scheduler.add_job(_run_global_macro_job, 'cron', hour=6, minute=50, id='batch_global_macro_briefings', replace_existing=True)
    scheduler.add_job(_run_international_macro_job, 'cron', hour=6, minute=53, id='batch_international_macro_briefings', replace_existing=True)
    scheduler.add_job(_run_global_calendar_job, 'cron', hour=6, minute=55, id='batch_global_event_calendars', replace_existing=True)
    scheduler.add_job(_run_global_issue_job, 'cron', hour=7, minute=5, id='batch_global_issue_stream', replace_existing=True)
    scheduler.add_job(_run_naver_headline_job, 'cron', hour=7, minute=7, id='batch_naver_headlines', replace_existing=True)
    scheduler.add_job(_run_market_regime_snapshot_job, 'cron', hour=7, minute=10, id='batch_market_regime_snapshot', replace_existing=True)
    return scheduler
