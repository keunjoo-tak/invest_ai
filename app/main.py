from fastapi import FastAPI

from app.api.routes.analysis import router as analysis_router
from app.api.routes.health import router as health_router
from app.api.routes.internal import router as internal_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine
from app.workers.scheduler import build_scheduler

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)
app.include_router(internal_router, prefix=settings.api_prefix)

scheduler = build_scheduler()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler.shutdown(wait=False)
