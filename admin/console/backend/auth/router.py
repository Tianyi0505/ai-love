from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .credentials import CredentialService, CurrentPasswordMismatch
from .login import InvalidCredentials, LoginService
from .schemas import (
    CredentialUpdateRequest,
    LoginRequest,
    MessageResponse,
    SessionResponse,
)
from .session import COOKIE_NAME, SESSION_TTL_SECONDS, RedisSessionStore


router = APIRouter(prefix="/ai-love-api", tags=["auth"])


def _login_service(request: Request) -> LoginService:
    return request.app.state.login_service


def _credential_service(request: Request) -> CredentialService:
    return request.app.state.credential_service


def _session_store(request: Request) -> RedisSessionStore:
    return request.app.state.session_store


async def require_session(
    request: Request,
    sessions: RedisSessionStore = Depends(_session_store),
) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if token is None or not await sessions.exists(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或会话已过期",
        )
    return token


@router.post("/login", response_model=SessionResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: LoginService = Depends(_login_service),
) -> SessionResponse:
    try:
        token, username = await service.login(payload.username, payload.password)
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        ) from exc
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return SessionResponse(
        authenticated=True,
        username=username,
        ai_id=request.app.state.config.ai_id,
    )


@router.get("/session", response_model=SessionResponse)
async def session(
    request: Request,
    _: str = Depends(require_session),
    service: LoginService = Depends(_login_service),
) -> SessionResponse:
    return SessionResponse(
        authenticated=True,
        username=await service.username(),
        ai_id=request.app.state.config.ai_id,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    sessions: RedisSessionStore = Depends(_session_store),
) -> MessageResponse:
    token = request.cookies.get(COOKIE_NAME)
    if token is not None:
        await sessions.delete(token)
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    return MessageResponse(message="已退出登录")


@router.post(
    "/credentials",
    response_model=MessageResponse,
    dependencies=[Depends(require_session)],
)
async def update_credentials(
    payload: CredentialUpdateRequest,
    response: Response,
    service: CredentialService = Depends(_credential_service),
) -> MessageResponse:
    try:
        await service.update(
            payload.current_password,
            payload.username,
            payload.password,
        )
    except CurrentPasswordMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        ) from exc
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    return MessageResponse(message="凭据已更新，请重新登录")
