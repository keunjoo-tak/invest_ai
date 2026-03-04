from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["web"])

_WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@router.get("/app", summary="웹 대시보드", description="InvestAI 웹 UI를 반환합니다.")
def web_app() -> FileResponse:
    """정적 웹 앱 진입점."""
    return FileResponse(_WEB_DIR / "index.html")

