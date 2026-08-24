from __future__ import annotations

from datetime import datetime

from shared.contracts.entity import EntityCandidate
from shared.contracts.rpc.rpc_model import RpcModel
from shared.contracts.tools import ToolExecutionContext


class ResolvePeopleRequest(RpcModel):
    context: ToolExecutionContext
    mention: str


class ResolvePeopleResponse(RpcModel):
    mention: str
    candidates: list[EntityCandidate]


class SearchGroupHistoryRequest(RpcModel):
    context: ToolExecutionContext
    query: str
    limit: int | None = None


class HistorySender(RpcModel):
    person_id: str
    display_name: str
    role: str


class HistoryMessage(RpcModel):
    message_id: str
    sender: HistorySender
    text: str
    occurred_at: datetime


class SearchGroupHistoryResponse(RpcModel):
    messages: list[HistoryMessage]
