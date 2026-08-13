
from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx

from ai.llm.service import ChatMessage, ChatRequest, ChatStreamChunk, LLMProvider, ToolCall, llm_registry
from shared.infrastructure.runtime_config import ConfigKey, required_setting


@llm_registry.register("ollama")
class OllamaProvider(LLMProvider):
    def __init__(self, model: str, request_timeout_sec: float, base_url: str | None = None, **_) -> None:
        self._url = required_setting(base_url, ConfigKey.OLLAMA_BASE_URL).rstrip("/")
        self._model = model
        self._request_timeout_sec = request_timeout_sec

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "stream": True,
        }
        if req.tools:
            payload["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in req.tools
            ]

        t0 = time.perf_counter()
        sent_first = False
        async with httpx.AsyncClient(timeout=self._request_timeout_sec) as client:
            async with client.stream("POST", f"{self._url}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if not sent_first:
                        sent_first = True
                        latency = int((time.perf_counter() - t0) * 1000)
                    else:
                        latency = 0
                    if data.get("done"):
                        yield ChatStreamChunk(finish_reason="stop", latency_ms=latency)
                    elif data.get("message", {}).get("content"):
                        yield ChatStreamChunk(content=data["message"]["content"], latency_ms=latency)
