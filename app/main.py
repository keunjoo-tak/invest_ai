import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.auth import router as auth_router
from app.api.routes.batch_ingestion import router as batch_ingestion_router
from app.api.routes.decision_products import router as decision_products_router
from app.api.routes.health import router as health_router
from app.api.routes.ingestion_pipeline import router as ingestion_pipeline_router
from app.api.routes.internal import router as internal_router
from app.api.routes.market_pulse import router as market_pulse_router
from app.api.routes.scheduler_control import router as scheduler_control_router
from app.api.routes.stock_insight import router as stock_insight_router
from app.api.routes.trade_compass import router as trade_compass_router
from app.api.routes.web import router as web_router
from app.core.config import get_settings
from app.services.auth.session_manager import COOKIE_NAME, parse_session_cookie
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.runtime_schema import ensure_runtime_schema
from app.db.session import engine
from app.workers.scheduler import build_scheduler

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name, version="0.3.0")

cors_allowed_origins = settings.cors_allowed_origins()
if cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins,
        allow_credentials=cors_allowed_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

trusted_hosts = settings.trusted_hosts()
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)


EXEMPT_PATH_PREFIXES = ("/assets", "/api/v1/internal/scheduler")
EXEMPT_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/app/login",
}


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """인증이 필요한 경로에 대해 세션을 확인한다."""
    if not settings.auth_enabled:
        return await call_next(request)

    path = request.url.path
    if path in EXEMPT_PATHS or any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES):
        return await call_next(request)

    auth_user = parse_session_cookie(request.cookies.get(COOKIE_NAME), settings.auth_secret_key)
    if auth_user:
        return await call_next(request)

    if path.startswith(settings.api_prefix) or path in {"/docs", "/openapi.json", "/redoc"}:
        return JSONResponse(status_code=401, content={"detail": "인증이 필요합니다."})

    if path.startswith("/app") or path == "/":
        return RedirectResponse(url="/app/login", status_code=303)

    return await call_next(request)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)
app.include_router(decision_products_router, prefix=settings.api_prefix)
app.include_router(internal_router, prefix=settings.api_prefix)
app.include_router(stock_insight_router, prefix=settings.api_prefix)
app.include_router(trade_compass_router, prefix=settings.api_prefix)
app.include_router(market_pulse_router, prefix=settings.api_prefix)
app.include_router(scheduler_control_router, prefix=settings.api_prefix)
app.include_router(ingestion_pipeline_router, prefix=settings.api_prefix)
app.include_router(batch_ingestion_router, prefix=settings.api_prefix)
app.include_router(web_router)
app.mount("/assets", StaticFiles(directory="app/web"), name="assets")

scheduler = build_scheduler()


@app.on_event("startup")
def on_startup() -> None:
    """애플리케이션 시작 시 스키마와 스케줄러를 준비한다."""
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    if settings.enable_scheduler:
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    """애플리케이션 종료 시 스케줄러를 정리한다."""
    if settings.enable_scheduler and scheduler.running:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    import uvicorn

    reload_enabled = os.getenv("INVESTAI_UVICORN_RELOAD", "false").lower() == "true"
    uvicorn.run("app.main:app", host=settings.server_host, port=settings.server_port, reload=reload_enabled)

