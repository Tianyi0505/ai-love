from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ops.panel.backend.auth.router import require_session

from .people_memory import InvalidPersonId, PeopleMemoryReader
from .personality import PersonalityReader
from .schemas import (
    PeopleResponse,
    PersonalityResponse,
    PersonMemoryResponse,
    QuickEntriesResponse,
    QuickEntry,
    SelfMemoryResponse,
)
from .self_memory import SelfMemoryReader
from .sso import create_dashboard_session, create_nacos_access_token

router = APIRouter(
    prefix="/ai-love-api",
    tags=["observability"],
    dependencies=[Depends(require_session)],
)


@router.get("/entries", response_model=QuickEntriesResponse)
async def entries(request: Request) -> QuickEntriesResponse:
    config = request.app.state.config
    napcat_query = urlencode({"token": config.napcat_token})
    return QuickEntriesResponse(
        entries=[
            QuickEntry(
                key="nacos",
                name="Nacos",
                description="配置中心",
                url="/ai-love-api/sso/nacos",
            ),
            QuickEntry(
                key="napcat",
                name="NapCat",
                description="QQ 连接与 WebUI",
                url=f"{config.napcat_url}?{napcat_query}",
            ),
            QuickEntry(
                key="k8s",
                name="Kubernetes",
                description="集群工作负载",
                url="/ai-love-api/sso/dashboard",
            ),
        ]
    )


@router.get("/sso/nacos", response_class=HTMLResponse)
async def nacos_sso(request: Request) -> HTMLResponse:
    config = request.app.state.config
    try:
        token = create_nacos_access_token(
            config.nacos_auth_token,
            config.nacos_sso_username,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nacos 自动登录配置不可用",
        ) from exc

    storage_value = json.dumps(
        {"accessToken": token, "username": config.nacos_sso_username},
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    redirect_url = json.dumps(config.nacos_url)
    return HTMLResponse(
        content=(
            "<!doctype html><meta charset=utf-8><title>正在进入 Nacos</title>"
            f"<script>localStorage.setItem('token',JSON.stringify({storage_value}));"
            f"location.replace({redirect_url});</script>"
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/sso/dashboard")
async def dashboard_sso(request: Request) -> RedirectResponse:
    config = request.app.state.config
    try:
        token = await create_dashboard_session(
            config.k8s_internal_url,
            config.k8s_service_account_token_path,
        )
    except (OSError, KeyError, ValueError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes Dashboard 自动登录失败",
        ) from exc

    response = RedirectResponse(config.k8s_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "token",
        token,
        path=config.k8s_url,
        httponly=False,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/personality", response_model=PersonalityResponse)
async def personality(
    request: Request,
) -> PersonalityResponse:
    reader: PersonalityReader = request.app.state.personality_reader
    return await reader.read(request.app.state.config.ai_id)


@router.get("/self-memory", response_model=SelfMemoryResponse)
async def self_memory(
    request: Request,
) -> SelfMemoryResponse:
    reader: SelfMemoryReader = request.app.state.self_memory_reader
    return await reader.read(request.app.state.config.ai_id)


@router.get("/people", response_model=PeopleResponse)
async def people(
    request: Request,
    q: str = Query(default=""),
) -> PeopleResponse:
    reader: PeopleMemoryReader = request.app.state.people_memory_reader
    return await reader.list(request.app.state.config.ai_id, q.strip())


@router.get("/people/{person_id}/memory", response_model=PersonMemoryResponse)
async def person_memory(
    person_id: str,
    request: Request,
) -> PersonMemoryResponse:
    reader: PeopleMemoryReader = request.app.state.people_memory_reader
    try:
        result = await reader.detail(request.app.state.config.ai_id, person_id)
    except InvalidPersonId as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="person_id 无效",
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="人物长期记忆不存在",
        )
    return result
