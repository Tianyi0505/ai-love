from __future__ import annotations

import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from ai.llm.providers.base import StreamingChatProvider
from ai.llm.types import ChatMessage, ChatRequest, ChatStreamChunk, ToolCall, ToolSchema


# 提供OpenAI兼容聊天协议的模板实现
class OpenAICompatibleProvider(StreamingChatProvider):
    # 初始化OpenAI兼容客户端
    def __init__(
        self,
        model: str,
        max_tokens: int,
        request_timeout_sec: float,
        api_key: str,
        base_url: str,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=request_timeout_sec,
        )
        self._model = model
        self._max_tokens = max_tokens

    # 转换为OpenAI兼容消息列表
    @staticmethod
    def _to_messages(messages: list[ChatMessage]) -> list[dict]:
        result = []
        for message in messages:
            item: dict = {"role": message.role, "content": message.content}
            if message.name:
                item["name"] = message.name
            result.append(item)
        return result

    # 转换为OpenAI兼容工具列表
    @staticmethod
    def _to_tools(tools: list[ToolSchema]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    # 组装OpenAI兼容请求参数
    def _build_request(self, req: ChatRequest) -> dict:
        kwargs: dict = {
            "model": self._model,
            "messages": self._to_messages(req.messages),
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if req.tools:
            kwargs["tools"] = self._to_tools(req.tools)
            kwargs["tool_choice"] = "auto"
        if "temperature" in req.options:
            kwargs["temperature"] = req.options["temperature"]
        return kwargs

    # 按OpenAI兼容协议读取流式响应
    async def _chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        tool_calls: dict[int, dict[str, str]] = {}
        stream = await self._client.chat.completions.create(**self._build_request(req))
        async for chunk in stream:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta
            for tool_delta in delta.tool_calls or []:
                index = tool_delta.index or 0
                pending = tool_calls.setdefault(index, {"name": "", "arguments": ""})
                function = tool_delta.function
                if function:
                    pending["name"] += function.name or ""
                    pending["arguments"] += function.arguments or ""

            if delta.content:
                yield ChatStreamChunk(content=delta.content)

            if choice.finish_reason:
                if choice.finish_reason == "tool_calls":
                    for pending in tool_calls.values():
                        yield ChatStreamChunk(
                            tool_call=ToolCall(
                                name=pending["name"],
                                arguments=self._parse_tool_arguments(pending["arguments"]),
                            )
                        )
                yield ChatStreamChunk(finish_reason=choice.finish_reason)

    # 解析流式拼接后的工具参数
    @staticmethod
    def _parse_tool_arguments(arguments: str) -> dict:
        if not arguments:
            return {}
        try:
            value = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    # 关闭资源
    async def close(self) -> None:
        await self._client.close()
