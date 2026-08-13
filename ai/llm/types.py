from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str
    content: str
    name: str = ""


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class ChatRequest:
    ai_id: str
    messages: list[ChatMessage]
    tools: list[ToolSchema] = field(default_factory=list)
    options: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class ChatStreamChunk:
    content: str = ""
    finish_reason: str = ""
    tool_call: ToolCall | None = None
    latency_ms: int = 0
