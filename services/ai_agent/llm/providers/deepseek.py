
from __future__ import annotations

import os
import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from services.ai_agent.llm.service import ChatMessage, ChatRequest, ChatStreamChunk, LLMProvider, ToolCall, ToolSchema, llm_registry
from shared.infrastructure.runtime_config import required_setting, required_value


@llm_registry.register("deepseek")
class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=required_setting(base_url, "DEEPSEEK_BASE_URL"),
        )
        self._model = required_value(model, "模型路由中的 DeepSeek 模型 ID")

    def _to_messages(self, msgs: list[ChatMessage]) -> list[dict]:
        out = []
        for m in msgs:
            item: dict = {"role": m.role, "content": m.content}
            if m.name:
                item["name"] = m.name
            out.append(item)
        return out

    def _to_tools(self, tools: list[ToolSchema]) -> list[dict]:
        return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}} for t in tools]

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        kwargs: dict = {"model": self._model, "messages": self._to_messages(req.messages), "stream": True}
        if req.tools:
            kwargs["tools"] = self._to_tools(req.tools)
            kwargs["tool_choice"] = "auto"
        if "temperature" in req.options:
            kwargs["temperature"] = req.options["temperature"]

        t0 = time.perf_counter()
        sent_first = False
        async for chunk in await self._client.chat.completions.create(**kwargs):
            if not sent_first:
                sent_first = True
                latency = int((time.perf_counter() - t0) * 1000)
            else:
                latency = 0
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            tool_calls = delta.tool_calls
            if tool_calls:
                tc = tool_calls[0]
                yield ChatStreamChunk(
                    tool_call=ToolCall(name=tc.function.name or "", arguments=tc.function.arguments or ""),
                    latency_ms=latency,
                )
            elif delta.content:
                yield ChatStreamChunk(content=delta.content, latency_ms=latency)
            elif chunk.choices[0].finish_reason:
                yield ChatStreamChunk(finish_reason=chunk.choices[0].finish_reason, latency_ms=latency)
