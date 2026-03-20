from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.workers.job_registry import list_scheduler_jobs, run_scheduler_job


def _run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        run_scheduler_job(job_id=job_id, db=db)
    finally:
        db.close()



def build_scheduler() -> BackgroundScheduler:
    """배치 스케줄러를 구성한다."""

    scheduler = BackgroundScheduler()
    for job in list_scheduler_jobs():
        scheduler.add_job(
            lambda current_job_id=job.job_id: _run_job(current_job_id),
            'cron',
            hour=job.schedule_hour,
            minute=job.schedule_minute,
            timezone=job.timezone,
            id=f'batch_{job.job_id}',
            replace_existing=True,
        )
    return scheduler
