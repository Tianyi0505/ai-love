from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai.llm.anthropic_compatible import AnthropicCompatibleProvider
from ai.llm.openai_compatible import OpenAICompatibleProvider
from ai.llm.providers.deepseek import DeepSeekProvider
from ai.llm.providers.deepseek_v4_flash_0731 import DeepSeekV4Flash0731Provider
from ai.llm.providers.ollama import OllamaProvider
from ai.llm.registry import provider_registry
from ai.llm.types import ChatMessage, ChatRequest, ToolSchema


class _AsyncItems:
    def __init__(self, items) -> None:
        self._items = items

    async def __aiter__(self):
        for item in self._items:
            yield item


class _OpenAICreate:
    def __init__(self, chunks) -> None:
        self._chunks = chunks
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return _AsyncItems(self._chunks)


class _AnthropicStream(_AsyncItems):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _AnthropicMessages:
    def __init__(self, events) -> None:
        self._events = events
        self.kwargs = None

    def stream(self, **kwargs):
        self.kwargs = kwargs
        return _AnthropicStream(self._events)


def _openai_chunk(*, content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tool_delta(index: int, *, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, function=function)


class OpenAICompatibleProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_and_fragmented_tool_call_follow_openai_template(self) -> None:
        create = _OpenAICreate(
            [
                SimpleNamespace(choices=[]),
                _openai_chunk(
                    tool_calls=[
                        _tool_delta(0, name="resolve_people", arguments='{"mention":')
                    ]
                ),
                _openai_chunk(
                    tool_calls=[_tool_delta(0, arguments='"老王"}')]
                ),
                _openai_chunk(finish_reason="tool_calls"),
            ]
        )
        provider = object.__new__(OpenAICompatibleProvider)
        provider._model = "model"
        provider._max_tokens = 512
        provider._client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create.create))
        )
        request = ChatRequest(
            ai_id="ai",
            messages=[
                ChatMessage(role="system", content="system"),
                ChatMessage(role="user", content="hello", name="tester"),
            ],
            tools=[
                ToolSchema(
                    name="resolve_people",
                    description="resolve",
                    parameters={"type": "object"},
                )
            ],
            options={"temperature": 0.2},
        )

        chunks = [chunk async for chunk in provider.chat_stream(request)]

        self.assertEqual(2, len(chunks))
        self.assertEqual("resolve_people", chunks[0].tool_call.name)
        self.assertEqual({"mention": "老王"}, chunks[0].tool_call.arguments)
        self.assertEqual("tool_calls", chunks[1].finish_reason)
        self.assertGreaterEqual(chunks[0].latency_ms, 0)
        self.assertEqual(0, chunks[1].latency_ms)
        self.assertEqual("model", create.kwargs["model"])
        self.assertEqual(512, create.kwargs["max_tokens"])
        self.assertEqual("tester", create.kwargs["messages"][1]["name"])
        self.assertEqual("auto", create.kwargs["tool_choice"])
        self.assertEqual(0.2, create.kwargs["temperature"])


class AnthropicCompatibleProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_system_prompt_and_tool_call_follow_anthropic_template(self) -> None:
        messages = _AnthropicMessages(
            [
                SimpleNamespace(
                    type="content_block_stop",
                    content_block=SimpleNamespace(
                        type="tool_use",
                        name="resolve_people",
                        input={"mention": "老王"},
                    ),
                ),
                SimpleNamespace(
                    type="message_delta",
                    delta=SimpleNamespace(stop_reason="tool_use"),
                ),
            ]
        )
        provider = object.__new__(AnthropicCompatibleProvider)
        provider._model = "model"
        provider._max_tokens = 512
        provider._client = SimpleNamespace(messages=messages)
        request = ChatRequest(
            ai_id="ai",
            messages=[
                ChatMessage(role="system", content="system-1"),
                ChatMessage(role="system", content="system-2"),
                ChatMessage(role="user", content="hello"),
            ],
            tools=[
                ToolSchema(
                    name="resolve_people",
                    description="resolve",
                    parameters={"type": "object"},
                )
            ],
            options={"temperature": 0.2},
        )

        chunks = [chunk async for chunk in provider.chat_stream(request)]

        self.assertEqual(2, len(chunks))
        self.assertEqual("resolve_people", chunks[0].tool_call.name)
        self.assertEqual({"mention": "老王"}, chunks[0].tool_call.arguments)
        self.assertEqual("tool_calls", chunks[1].finish_reason)
        self.assertEqual("system-1\nsystem-2", messages.kwargs["system"])
        self.assertEqual([{"role": "user", "content": "hello"}], messages.kwargs["messages"])
        self.assertEqual({"type": "object"}, messages.kwargs["tools"][0]["input_schema"])
        self.assertEqual(0.2, messages.kwargs["temperature"])


class ConcreteProviderTests(unittest.TestCase):
    def test_concrete_providers_only_select_protocol_and_connection(self) -> None:
        self.assertTrue(issubclass(DeepSeekProvider, OpenAICompatibleProvider))
        self.assertTrue(issubclass(OllamaProvider, OpenAICompatibleProvider))
        self.assertTrue(
            issubclass(DeepSeekV4Flash0731Provider, AnthropicCompatibleProvider)
        )
        self.assertIs(
            DeepSeekV4Flash0731Provider,
            provider_registry.get("deepseek_v4_flash_0731"),
        )

        with patch("ai.llm.openai_compatible.AsyncOpenAI") as client_type:
            OllamaProvider(
                model="qwen",
                max_tokens=512,
                request_timeout_sec=30,
                base_url="http://localhost:11434/",
            )

        client_type.assert_called_once_with(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            timeout=30,
        )


if __name__ == "__main__":
    unittest.main()
