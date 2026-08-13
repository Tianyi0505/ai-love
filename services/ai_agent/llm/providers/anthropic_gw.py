
from __future__ import annotations

import os
import time
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from services.ai_agent.llm.service import ChatMessage, ChatRequest, ChatStreamChunk, LLMProvider, ToolCall, ToolSchema, llm_registry
from shared.infrastructure.runtime_config import required_setting, required_value


@llm_registry.register("anthropic_gw")
class AnthropicGatewayProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._client = AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
            base_url=required_setting(base_url, "ANTHROPIC_BASE_URL"),
        )
        self._model = required_value(model, "模型路由中的 Anthropic 模型 ID")
        self._max_tokens = max_tokens

    def _to_messages(self, msgs: list[ChatMessage]) -> list[dict]:
        out = []
        for m in msgs:
            if m.role == "system":
                continue
            out.append({"role": "assistant" if m.role == "assistant" else "user", "content": m.content})
        return out

    def _to_tools(self, tools: list[ToolSchema]) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        system_prompt = "\n".join(m.content for m in req.messages if m.role == "system")
        kwargs: dict = {
            "model": self._model,
            "messages": self._to_messages(req.messages),
            "max_tokens": self._max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if req.tools:
            kwargs["tools"] = self._to_tools(req.tools)

        t0 = time.perf_counter()
        sent_first = False
        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if not sent_first:
                    sent_first = True
                    latency = int((time.perf_counter() - t0) * 1000)
                else:
                    latency = 0
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        self._tool_name = event.content_block.name
                        self._tool_input = ""
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield ChatStreamChunk(content=delta.text, latency_ms=latency)
                    elif delta.type == "thinking_delta":
                        yield ChatStreamChunk(content="", latency_ms=latency)
                    elif delta.type == "input_json_delta":
                        self._tool_input = getattr(self, "_tool_input", "") + delta.partial_json
                elif event.type == "message_delta":
                    stop = event.delta.stop_reason
                    if stop == "tool_use":
                        yield ChatStreamChunk(
                            finish_reason="tool_calls",
                            tool_call=ToolCall(name=getattr(self, "_tool_name", ""), arguments=self._tool_input or {}),
                            latency_ms=latency,
                        )
                    elif stop == "end_turn":
                        yield ChatStreamChunk(finish_reason="stop", latency_ms=latency)

    async def close(self) -> None:
        await self._client.close()
