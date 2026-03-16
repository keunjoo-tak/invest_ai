from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.analysis import router as analysis_router
from app.api.routes.batch_ingestion import router as batch_ingestion_router
from app.api.routes.decision_products import router as decision_products_router
from app.api.routes.health import router as health_router
from app.api.routes.ingestion_pipeline import router as ingestion_pipeline_router
from app.api.routes.internal import router as internal_router
from app.api.routes.market_pulse import router as market_pulse_router
from app.api.routes.stock_insight import router as stock_insight_router
from app.api.routes.trade_compass import router as trade_compass_router
from app.api.routes.web import router as web_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.runtime_schema import ensure_runtime_schema
from app.db.session import engine
from app.workers.scheduler import build_scheduler

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name, version="0.3.0")
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)
app.include_router(decision_products_router, prefix=settings.api_prefix)
app.include_router(internal_router, prefix=settings.api_prefix)
app.include_router(stock_insight_router, prefix=settings.api_prefix)
app.include_router(trade_compass_router, prefix=settings.api_prefix)
app.include_router(market_pulse_router, prefix=settings.api_prefix)
app.include_router(ingestion_pipeline_router, prefix=settings.api_prefix)
app.include_router(batch_ingestion_router, prefix=settings.api_prefix)
app.include_router(web_router)
app.mount("/assets", StaticFiles(directory="app/web"), name="assets")

scheduler = build_scheduler()


@app.on_event("startup")
def on_startup() -> None:
    """애플리케이션 시작 시 스키마와 스케줄러를 초기화한다."""
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    """애플리케이션 종료 시 스케줄러를 정리한다."""
    scheduler.shutdown(wait=False)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=5000, reload=True)
