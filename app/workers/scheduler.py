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


def build_scheduler() -> BackgroundScheduler:
    """동작 설명은 인수인계 문서를 참고하세요."""
    scheduler = BackgroundScheduler()
    # 정책 브리핑 문서 배치(매일 06:15 KST)
    scheduler.add_job(_run_policy_briefing_job, "cron", hour=6, minute=15, id="batch_policy_briefing", replace_existing=True)
    # 한국은행 문서 배치(매일 06:35 KST)
    scheduler.add_job(_run_bok_job, "cron", hour=6, minute=35, id="batch_bok_publications", replace_existing=True)
    return scheduler
