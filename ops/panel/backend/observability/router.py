from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ops.panel.backend.auth.router import require_session

from .people_memory import InvalidPersonId, PeopleMemoryReader
from .personality import PersonalityReader
from .schemas import (
    PeopleResponse,
    PersonMemoryResponse,
    PersonalityResponse,
    QuickEntriesResponse,
    QuickEntry,
    SelfMemoryResponse,
)
from .self_memory import SelfMemoryReader


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
                url=config.nacos_url,
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
                url=config.k8s_url,
            ),
        ]
    )


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
