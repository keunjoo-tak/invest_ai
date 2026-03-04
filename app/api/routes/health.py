from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="헬스체크",
    description="API 서버 상태, 실행 환경, 현재 UTC 시각을 반환합니다.",
)
def health() -> HealthResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        env=settings.app_env,
        time_utc=datetime.now(timezone.utc),
    )
