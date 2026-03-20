from __future__ import annotations

from hmac import compare_digest

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.auth.session_manager import COOKIE_NAME, build_session_cookie, parse_session_cookie

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """로그인 요청 본문."""

    username: str = Field(..., description="로그인 사용자명")
    password: str = Field(..., description="로그인 비밀번호")


@router.post("/login", summary="로그인", description="사용자 로그인 세션을 생성합니다.")
def login(payload: LoginRequest, response: Response) -> dict[str, object]:
    """사용자 인증 후 세션 쿠키를 설정한다."""
    settings = get_settings()
    if not settings.auth_enabled:
        return {"ok": True, "auth_enabled": False, "username": payload.username}

    valid_user = compare_digest(payload.username, settings.auth_username)
    valid_password = compare_digest(payload.password, settings.auth_password)
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="로그인 정보가 올바르지 않습니다.")

    cookie_value = build_session_cookie(
        username=settings.auth_username,
        secret_key=settings.auth_secret_key,
        max_age_seconds=settings.auth_session_max_age_seconds,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.auth_session_max_age_seconds,
        path="/",
    )
    return {"ok": True, "auth_enabled": True, "username": settings.auth_username}


@router.post("/logout", summary="로그아웃", description="현재 세션을 종료합니다.")
def logout(response: Response) -> dict[str, object]:
    """로그아웃 쿠키를 제거한다."""
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", summary="세션 확인", description="현재 로그인 상태를 확인합니다.")
def me(request: Request) -> dict[str, object]:
    """현재 로그인 세션 정보를 반환한다."""
    settings = get_settings()
    if not settings.auth_enabled:
        return {"authenticated": True, "auth_enabled": False, "username": "dev-local"}

    auth_user = parse_session_cookie(request.cookies.get(COOKIE_NAME), settings.auth_secret_key)
    if not auth_user:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return {"authenticated": True, "auth_enabled": True, "username": auth_user.get("username", settings.auth_username)}
