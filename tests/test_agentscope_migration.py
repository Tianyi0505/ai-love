import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agentscope.message import DataBlock, TextBlock, ToolCallBlock, ToolResultBlock, UserMsg
from agentscope.model import AnthropicChatModel, ChatResponse, DeepSeekChatModel, OpenAIChatModel
from output_fixtures import ScriptedModel, ValidatingOutputClient, tool_call
from test_agnes_models import settings

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.response_output_policy import ResponseOutputPolicy
from shared.agent_output import StructuredOutput
from shared.chat_model_factory import create_chat_model, create_openai_compatible_chat_model
from shared.contracts.response_output import Emotion, ParticipationDecision, ResponsePlan, Speech
from shared.contracts.tools import ToolExecutionContext
from shared.global_settings import ChatModelSettings
from shared.model_observability import record_messages_usage

PLAN = ResponsePlan(speech=[Speech(text="你好", delivery="text")], emotion=Emotion(name="happy", intensity=0.5), actions=[])


def chat(model, output_client=None, **kwargs):
    config = settings()
    return ChatAgent(
        model, "test", [], ResponseOutputPolicy(config.llm.output_limits),
        max_requests=3, participation_max_requests=2, max_tokens=100, retry_count=1,
        observability=config.observability, output_client=output_client or ValidatingOutputClient(), **kwargs,
    )


@pytest.mark.parametrize("provider,model_type", [("openai", OpenAIChatModel), ("deepseek", DeepSeekChatModel),
                                               ("anthropic", AnthropicChatModel)])
async def test_factory_uses_native_sdk_and_catalog_credentials(monkeypatch, provider, model_type):
    monkeypatch.setenv("TEST_MODEL_KEY", "test-key")
    model = create_chat_model("test", models={"test": ChatModelSettings(
        provider=provider, model="test-model", base_url="https://example.com/v1", api_key_env="TEST_MODEL_KEY",
    )}, max_tokens=200, timeout_sec=21, max_retries=2)
    try:
        assert isinstance(model, model_type)
        assert model.credential.api_key.get_secret_value() == "test-key"
        assert model.credential.base_url == "https://example.com/v1"
        assert model.parameters.max_tokens == 200
        assert model.client_kwargs == {"timeout": 21, "max_retries": 0}
        assert model.max_retries == 2
        assert not model.stream
    finally:
        await model.client.close()


async def test_compatible_factory_uses_legacy_token_parameter():
    model = create_openai_compatible_chat_model(
        "vision", api_key="test", base_url="https://example.com/v1", max_tokens=200, timeout_sec=20, max_retries=0,
    )
    try:
        assert isinstance(model, OpenAIChatModel)
        assert model.extra_body == {"max_tokens": 200}
        assert model.parameters.max_tokens is None
    finally:
        await model.client.close()


async def test_chat_and_participation_keep_images_and_trusted_mcp_context():
    decision = ParticipationDecision(participate=True, reason="被明确提问")
    model = ScriptedModel([tool_call(PLAN), tool_call(PLAN), tool_call(decision)])
    client = SimpleNamespace(submit=AsyncMock(wraps=ValidatingOutputClient().submit))
    agent = chat(model, client)
    images = [ImageAttachment(source_url="https://example.com/a.jpg", data_url="data:image/jpeg;base64,YQ==",
                              attribution="甲的图片")]
    context = ToolExecutionContext(chat_id="trusted")
    assert await agent.generate_plan("身份", "你好", allow_tools=False, images=images, tool_context=context) == PLAN
    assert await agent.generate_plan("身份", "你好", images=images, tool_context=context) == PLAN
    assert await agent.decide_participation("身份", "你好", images=images) == decision
    for messages in model.requests:
        assert messages[0].get_text_content() == "身份"
        assert any(isinstance(block, DataBlock) and block.source.media_type == "image/jpeg"
                   for block in messages[1].content)
        assert "甲的图片" in messages[1].get_text_content()
    assert all(call.args[2] == context for call in client.submit.await_args_list[:2])


async def test_native_schema_repair_and_total_request_budget():
    invalid = ChatResponse(content=[ToolCallBlock(id="bad", name="GenerateStructuredOutput", input='{"speech":"bad"}')],
                           is_last=True)
    model = ScriptedModel([invalid, tool_call(PLAN)])
    assert await chat(model).generate_plan("身份", "你好", allow_tools=False) == PLAN
    assert len(model.requests) == 2
    assert any(isinstance(block, ToolResultBlock) for msg in model.requests[1] for block in msg.content)
    raw = ChatResponse(content=[TextBlock(text="没有结构化结果")], is_last=True)
    exhausted = ScriptedModel([raw, raw, raw])
    with pytest.raises(ValueError, match="限额"):
        await chat(exhausted).generate_plan("身份", "你好")
    assert len(exhausted.requests) == 3


async def test_shared_chat_keeps_concurrent_turns_isolated():
    both_started = asyncio.Event()
    count = 0

    async def respond(messages, tools):
        nonlocal count
        count += 1
        if count == 2:
            both_started.set()
        await both_started.wait()
        return tool_call(PLAN)

    model = ScriptedModel(callback=respond)
    client = SimpleNamespace(submit=AsyncMock(wraps=ValidatingOutputClient().submit))
    agent = chat(model, client)
    await asyncio.wait_for(asyncio.gather(*[
        agent.generate_plan("身份", text, tool_context=ToolExecutionContext(chat_id=text)) for text in ("甲", "乙")
    ]), 5)
    assert {messages[1].get_text_content() for messages in model.requests} == {"甲", "乙"}
    assert {call.args[2].chat_id for call in client.submit.await_args_list} == {"甲", "乙"}
    assert all({m.get_text_content() for m in messages if m.role == "user" and m.get_text_content()}
               == {messages[1].get_text_content()} for messages in model.requests)


async def test_cancellation_does_not_submit_a_partial_result():
    started = asyncio.Event()

    async def respond(messages, tools):
        started.set()
        await asyncio.Event().wait()

    client = SimpleNamespace(submit=AsyncMock())
    task = asyncio.create_task(chat(ScriptedModel(callback=respond), client).generate_plan("身份", "你好"))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.submit.assert_not_awaited()


async def test_sdk_aggregated_usage_is_recorded_without_content():
    model = ScriptedModel([tool_call(PLAN, {"input_tokens": 3, "output_tokens": 5})])
    result = await StructuredOutput(model, ResponsePlan, 1, ValidatingOutputClient()).generate([UserMsg("user", "你好")])
    span = Mock()
    record_messages_usage(span, [result["raw"]])
    assert dict(call.args for call in span.set_attribute.call_args_list) == {
        "gen_ai.usage.input_tokens": 3, "gen_ai.usage.output_tokens": 5, "gen_ai.usage.total_tokens": 8,
    }
