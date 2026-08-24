from __future__ import annotations

from typing import Any

from shared.contracts.rpc.rpc_model import RpcModel
from shared.contracts.tools import ToolExecutionContext


class MemorySearchRequest(RpcModel):
    ai_id: str
    query: str
    top_k: int
    person_id: str | None
    session_id: str | None
    active_session_actors: list[str]


class MemorySearchItem(RpcModel):
    memory_id: str
    person_id: str
    content: str
    memory_type: str
    scope: str
    confidence: float
    retrieval_score: float


class MemorySearchResponse(RpcModel):
    results: list[MemorySearchItem]


class MemoryContextRequest(RpcModel):
    ai_id: str
    person_id: str | None
    conversation_id: str | None


class MemoryContextResponse(RpcModel):
    self_markdown: str
    person_markdown: str
    conversation_summary: str


class PersonContextRequest(RpcModel):
    context: ToolExecutionContext
    person_id: str


class PersonFact(RpcModel):
    content: str
    type: str
    importance: float
    confidence: float


class PersonContextResponse(RpcModel):
    person_id: str
    scene: str
    facts: list[PersonFact]
    conversation_summary: str


class MemoryPipelineEvent(RpcModel):
    event: str
    data: dict[str, Any]
