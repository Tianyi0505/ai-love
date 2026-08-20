from __future__ import annotations

from typing import AsyncIterator

from anthropic import AsyncAnthropic

from ai.llm.providers.base import StreamingChatProvider
from ai.llm.types import ChatMessage, ChatRequest, ChatStreamChunk, ToolCall, ToolSchema


# 提供Anthropic兼容聊天协议的模板实现
class AnthropicCompatibleProvider(StreamingChatProvider):
    # 初始化Anthropic兼容客户端
    def __init__(
        self,
        model: str,
        max_tokens: int,
        request_timeout_sec: float,
        api_key: str,
        base_url: str,
    ) -> None:
        self._client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=request_timeout_sec,
        )
        self._model = model
        self._max_tokens = max_tokens

    # 转换为Anthropic兼容消息列表
    @staticmethod
    def _to_messages(messages: list[ChatMessage]) -> list[dict]:
        return [
            {
                "role": "assistant" if message.role == "assistant" else "user",
                "content": message.content,
            }
            for message in messages
            if message.role != "system"
        ]

    # 转换为Anthropic兼容工具列表
    @staticmethod
    def _to_tools(tools: list[ToolSchema]) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    # 组装Anthropic兼容请求参数
    def _build_request(self, req: ChatRequest) -> dict:
        kwargs: dict = {
            "model": self._model,
            "messages": self._to_messages(req.messages),
            "max_tokens": self._max_tokens,
        }
        system_prompt = "\n".join(
            message.content for message in req.messages if message.role == "system"
        )
        if system_prompt:
            kwargs["system"] = system_prompt
        if req.tools:
            kwargs["tools"] = self._to_tools(req.tools)
        if "temperature" in req.options:
            kwargs["temperature"] = req.options["temperature"]
        return kwargs

    # 按Anthropic兼容协议读取流式响应
    async def _chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        async with self._client.messages.stream(**self._build_request(req)) as stream:
            async for event in stream:
                if event.type == "text":
                    yield ChatStreamChunk(content=event.text)
                elif event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta":
                        yield ChatStreamChunk()
                elif (
                    event.type == "content_block_stop"
                    and event.content_block.type == "tool_use"
                ):
                    block = event.content_block
                    yield ChatStreamChunk(
                        tool_call=ToolCall(
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        )
                    )
                elif event.type == "message_delta" and event.delta.stop_reason:
                    yield ChatStreamChunk(
                        finish_reason=self._to_finish_reason(event.delta.stop_reason)
                    )

    # 转换Anthropic结束原因
    @staticmethod
    def _to_finish_reason(reason: str) -> str:
        return {
            "end_turn": "stop",
            "tool_use": "tool_calls",
            "max_tokens": "length",
        }.get(reason, reason)

    # 关闭资源
    async def close(self) -> None:
        await self._client.close()
