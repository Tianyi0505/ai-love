from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.response_output_policy import ResponseOutputLimits, ResponseOutputPolicy
from agent.conversation.response_plan import Emotion, ParticipationDecision, ResponsePlan, Speech
from agent.vision.image_describer import ImageDescriber
from agent.vision.image_description import ImageDescription
from agent.vision.image_fetcher import FetchedImage
from memory.memory_generation_output import MemoryConsolidationOutput, MemoryExtractionOutput
from memory.memory_model_pool import MemoryModelPool
from shared.chat_model_factory import (
    create_chat_model,
    create_openai_compatible_chat_model,
)
from shared.contracts.tools import ToolExecutionContext
from shared.global_settings import ObservabilitySettings
from shared.langchain_structured_output import (
    parsed_output,
    structured_output_runnable,
)


def observability() -> ObservabilitySettings:
    return ObservabilitySettings(
        include_model_content=False,
        include_binary_content=False,
        include_model_request_parameters=True,
    )


class ChatModelFactoryTests(unittest.TestCase):
    @patch("shared.chat_model_factory.ChatDeepSeek")
    def test_deepseek_model_uses_provider_prefix_and_environment(self, model_class) -> None:
        model_class.return_value = MagicMock()
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-key",
                "DEEPSEEK_BASE_URL": "https://deepseek.example/v1",
            },
            clear=False,
        ):
            create_chat_model(
                "deepseek:deepseek-chat",
                max_tokens=100,
                timeout_sec=30,
                max_retries=1,
            )

        model_class.assert_called_once_with(
            model="deepseek-chat",
            api_key="deepseek-key",
            base_url="https://deepseek.example/v1",
            extra_body={"thinking": {"type": "disabled"}},
            max_tokens=100,
            timeout=30,
            max_retries=1,
        )

    @patch("shared.chat_model_factory.ChatAnthropic")
    def test_anthropic_model_uses_existing_auth_token(self, model_class) -> None:
        model_class.return_value = MagicMock()
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_AUTH_TOKEN": "anthropic-token",
                "ANTHROPIC_BASE_URL": "https://anthropic.example",
            },
            clear=False,
        ):
            create_chat_model(
                "anthropic:claude-test",
                max_tokens=100,
                timeout_sec=30,
                max_retries=1,
            )

        model_class.assert_called_once_with(
            model="claude-test",
            api_key="anthropic-token",
            base_url="https://anthropic.example",
            max_tokens=100,
            timeout=30,
            max_retries=1,
        )

    @patch("shared.chat_model_factory.ChatOpenAI")
    def test_openai_compatible_model_uses_explicit_endpoint(self, model_class) -> None:
        client = MagicMock()
        create_openai_compatible_chat_model(
            "qwen-vl-plus",
            api_key="bailian-key",
            base_url="https://dashscope.example/v1",
            max_tokens=200,
            timeout_sec=20,
            max_retries=0,
            http_async_client=client,
        )

        model_class.assert_called_once_with(
            model="qwen-vl-plus",
            api_key="bailian-key",
            base_url="https://dashscope.example/v1",
            max_tokens=200,
            timeout=20,
            max_retries=0,
            http_async_client=client,
        )


class ChatAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_and_agent_paths_return_structured_output(self) -> None:
        plan = ResponsePlan(
            speech=[Speech(text="你好", delivery="text")],
            emotion=Emotion(name="happy", intensity=0.5),
            actions=[],
        )
        decision = ParticipationDecision(participate=True, reason="被明确提问")
        raw = AIMessage(content="", usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
        plan_call = AsyncMock(
            return_value={"parsed": plan, "raw": raw, "parsing_error": None}
        )
        plan_runnable = RunnableLambda(plan_call)
        participation_call = AsyncMock(
            return_value={
                "parsed": decision,
                "raw": raw,
                "parsing_error": None,
            }
        )
        participation_runnable = RunnableLambda(participation_call)
        model = MagicMock()
        model.with_structured_output.side_effect = [
            plan_runnable,
            participation_runnable,
        ]
        graph = SimpleNamespace(
            ainvoke=AsyncMock(
                return_value={
                    "structured_response": plan,
                    "messages": [raw],
                }
            )
        )
        limits = ResponseOutputLimits(
            speech_min_chars=1,
            speech_max_chars=200,
            action_query_min_chars=1,
            action_query_max_chars=200,
            participation_reason_min_chars=1,
            participation_reason_max_chars=200,
            emotion_intensity_min=0,
            emotion_intensity_max=1,
        )
        with patch("agent.conversation.chat_agent.create_agent", return_value=graph):
            agent = ChatAgent(
                model=model,
                model_name="deepseek:deepseek-chat",
                tools=[],
                output_policy=ResponseOutputPolicy(limits),
                max_requests=4,
                participation_max_requests=1,
                max_tokens=100,
                retry_count=0,
                tool_retry_count=0,
                observability=observability(),
            )

        direct = await agent.generate_plan(
            "system",
            "user",
            allow_tools=False,
            images=[
                ImageAttachment(
                    source_url="https://example.com/image.jpg",
                    data_url="data:image/jpeg;base64,aW1hZ2U=",
                    attribution="小爱: [图片]",
                )
            ],
        )
        context = ToolExecutionContext(chat_id="trusted")
        with_tools = await agent.generate_plan(
            "system",
            "user",
            tool_context=context,
        )
        participation = await agent.decide_participation("system", "user")

        self.assertEqual(plan, direct)
        self.assertEqual(plan, with_tools)
        self.assertEqual(decision, participation)
        graph.ainvoke.assert_awaited_once()
        self.assertEqual(context, graph.ainvoke.await_args.kwargs["context"])
        direct_message = plan_call.await_args_list[0].args[0][1]
        self.assertEqual("user", direct_message.content[0]["text"])
        self.assertEqual("下图对应消息：小爱: [图片]", direct_message.content[1]["text"].strip())
        self.assertEqual(
            "data:image/jpeg;base64,aW1hZ2U=",
            direct_message.content[2]["image_url"]["url"],
        )


class ImageDescriberTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_is_sent_as_multimodal_structured_input(self) -> None:
        output = ImageDescription(
            description="一张图片",
            tags=["图片"],
            match_quality=0.5,
            emotion="neutral",
            sticker_description="普通图片",
        )
        raw = AIMessage(content="")
        invoke = AsyncMock(
            return_value={"parsed": output, "raw": raw, "parsing_error": None}
        )
        runnable = RunnableLambda(invoke)
        model = MagicMock()
        model.with_structured_output.return_value = runnable
        fetcher = SimpleNamespace(
            fetch=AsyncMock(
                return_value=FetchedImage(data=b"image", media_type="image/jpeg")
            )
        )
        policy = SimpleNamespace(validate=MagicMock(return_value=output))
        describer = ImageDescriber(
            model,
            "qwen-vl-plus",
            fetcher,
            policy,
            "描述图片",
            200,
            0,
            observability(),
        )

        result = await describer.describe("https://example.com/image.jpg")

        self.assertEqual(output, result)
        message = invoke.await_args.args[0][0]
        self.assertEqual("text", message.content[0]["type"])
        self.assertTrue(
            message.content[1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
        )


class MemoryModelPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_runnable_is_cached_by_fingerprint_and_output_type(self) -> None:
        definition = SimpleNamespace(
            fingerprint="v1",
            model_profile=SimpleNamespace(model="deepseek:deepseek-chat"),
        )
        definitions = SimpleNamespace(load=AsyncMock(return_value=definition))
        extraction = MemoryExtractionOutput(episode_summary="摘要", memories=[])
        consolidation = MemoryConsolidationOutput(markdown="# 文档")
        raw = AIMessage(content="")
        extraction_runnable = RunnableLambda(
            AsyncMock(
                return_value={
                    "parsed": extraction,
                    "raw": raw,
                    "parsing_error": None,
                }
            )
        )
        consolidation_runnable = RunnableLambda(
            AsyncMock(
                return_value={
                    "parsed": consolidation,
                    "raw": raw,
                    "parsing_error": None,
                }
            )
        )
        model = MagicMock()
        model.with_structured_output.side_effect = [
            extraction_runnable,
            consolidation_runnable,
        ]
        config = SimpleNamespace(
            max_tokens=100,
            provider_request_timeout_sec=30,
            retry_count=0,
            memory_max_requests=1,
        )
        pool = MemoryModelPool(definitions, config, observability())

        with patch(
            "memory.memory_model_pool.create_chat_model",
            return_value=model,
        ) as factory:
            loaded_definition, loaded_model = await pool.resources("ai")
            first = await pool.generate("ai", "prompt", MemoryExtractionOutput)
            second = await pool.generate("ai", "prompt", MemoryExtractionOutput)
            document = await pool.generate("ai", "prompt", MemoryConsolidationOutput)

        self.assertIs(definition, loaded_definition)
        self.assertIs(model, loaded_model)
        self.assertEqual(extraction, first)
        self.assertEqual(extraction, second)
        self.assertEqual(consolidation, document)
        factory.assert_called_once()
        self.assertEqual(2, model.with_structured_output.call_count)


class StructuredOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_parsing_error_retries_model_call(self) -> None:
        decision = ParticipationDecision(participate=True, reason="被明确提问")
        invoke = AsyncMock(
            side_effect=[
                {
                    "parsed": None,
                    "raw": AIMessage(content=""),
                    "parsing_error": ValueError("invalid output"),
                },
                {
                    "parsed": decision,
                    "raw": AIMessage(content=""),
                    "parsing_error": None,
                },
            ]
        )
        model = MagicMock()
        model.with_structured_output.return_value = RunnableLambda(invoke)
        runnable = structured_output_runnable(
            model,
            ParticipationDecision,
            max_attempts=2,
        )

        result = await runnable.ainvoke("prompt")

        self.assertEqual(decision, parsed_output(result, ParticipationDecision))
        self.assertEqual(2, invoke.await_count)


if __name__ == "__main__":
    unittest.main()
