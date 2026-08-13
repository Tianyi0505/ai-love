from __future__ import annotations

from dataclasses import dataclass, field


# 表示聊天消息数据
@dataclass
class ChatMessage:
    role: str
    content: str
    name: str = ""


# 表示工具结构数据
@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


# 表示聊天请求数据
@dataclass
class ChatRequest:
    ai_id: str
    messages: list[ChatMessage]
    tools: list[ToolSchema] = field(default_factory=list)
    options: dict = field(default_factory=dict)


# 描述工具调用数据
@dataclass
class ToolCall:
    name: str
    arguments: dict


# 描述聊天流式响应片段
@dataclass
class ChatStreamChunk:
    content: str = ""
    finish_reason: str = ""
    tool_call: ToolCall | None = None
    latency_ms: int = 0
