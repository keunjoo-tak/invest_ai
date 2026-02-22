from apscheduler.schedulers.background import BackgroundScheduler


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    # MVP: 실제 배치 잡은 운영 환경에서 큐 워커로 확장
    return scheduler
