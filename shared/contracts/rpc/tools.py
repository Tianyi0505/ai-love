from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.contracts.rpc.rpc_model import RpcModel
from shared.contracts.tools import ToolExecutionContext


class ToolListRequest(RpcModel):
    ai_id: str


class ToolDescriptor(RpcModel):
    name: str
    description: str
    parameters: dict[str, Any]
    provider: str


class ToolListResponse(RpcModel):
    tools: list[ToolDescriptor]


class ToolExecuteRequest(RpcModel):
    ai_id: str
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    execution_context: ToolExecutionContext
    reason: str = ""


class ToolExecuteResponse(RpcModel):
    content: str
    data: dict[str, Any] = Field(default_factory=dict)
