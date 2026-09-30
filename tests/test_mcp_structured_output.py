from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from mcp import Client
from output_fixtures import tool_call
from pydantic import Field, ValidationError
from test_plugin_runtime import command, manifest

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.response_output_policy import ResponseOutputPolicy
from agent.extension_toolset_loader import load_toolset
from plugin_runtime.control import PluginControlClient
from plugin_runtime.host import PluginHost
from shared.contracts.memory_output import MemoryConsolidationOutput, MemoryExtractionOutput
from shared.contracts.response_output import Emotion, ParticipationDecision, ResponsePlan, Speech
from shared.contracts.vision_output import ImageDescription, StickerDecision
from shared.global_settings import GlobalSettings
from shared.mcp_output_client import MCPOutputClient
from shared.nats_bus import RemoteCallError, create_bus
from shared.service_settings import ExtensionHostSettings
from shared.structured_output_tools import OUTPUT_TOOLS, GroupRepeatDecision, output_tool
from tests.test_memory_persona_integrity import FileConfiguration


class ScriptedToolModel(BaseChatModel):
    responses: list[AIMessage]
    requests: list = Field(default_factory=list)
    bindings: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "scripted-tool-model"

    def bind_tools(self, tools, **kwargs):
        self.bindings.append((tools, kwargs))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


@pytest.fixture
async def output_service(tmp_path):
    root = tmp_path / "catalog"
    manifest(root, "mcp.server", host="mcp", entrypoint="plugins.mcp:MCPServerPlugin",
             provides=("mcp.server",), config={"port": 0, "bind": "127.0.0.1"})
    (root / "structured-output").mkdir()
    (root / "structured-output/plugin.json").write_bytes(
        (Path(__file__).parents[1] / "plugins/catalog/structured-output/plugin.json").read_bytes()
    )
    manifest(root, "tools", host="extension-host", entrypoint="plugins.components:ServicePlugin",
             provides=("tools.gateway",),
             config={"implementation": "extensions.host.extension_host_service:ExtensionHostService"})
    bus = create_bus(os.environ["AILOVE_TEST_NATS_URL"], None)
    await bus.connect()
    mcp_host = PluginHost("mcp", bus=create_bus(os.environ["AILOVE_TEST_NATS_URL"], None),
                          roots=[root], state_directory=tmp_path / "state")
    await mcp_host.start()
    port = mcp_host.manager.resolve("mcp.server").http.servers[0].sockets[0].getsockname()[1]
    config = ExtensionHostSettings(
        instance_addr="127.0.0.1:0", binding_poll_interval_sec=3600, grounding_timeout_sec=1,
        mcp_url=f"http://127.0.0.1:{port}/mcp", messages={},
    )
    definition = SimpleNamespace(
        ai_id="test-ai", fingerprint="output-v1",
        extensions=[SimpleNamespace(enabled=True, permission="allow", tool_id=s.name, config={}) for s in OUTPUT_TOOLS],
    )
    cfg = SimpleNamespace(section=AsyncMock(return_value=config), config_provider=SimpleNamespace(close=AsyncMock()))
    extension = PluginHost("extension-host", bus=create_bus(os.environ["AILOVE_TEST_NATS_URL"], None),
                           roots=[root], state_directory=tmp_path / "state",
                           configuration=AsyncMock(return_value=cfg))
    settings = GlobalSettings.model_validate(await FileConfiguration().get("ailove.config"))
    try:
        with patch("extensions.host.extension_host_service.AgentDefinitionStore") as store:
            store.return_value.list_active = AsyncMock(return_value=[definition])
            await extension.start()
            yield SimpleNamespace(
                bus=bus, url=config.mcp_url, settings=settings, definition=definition,
                client=MCPOutputClient(bus, definition.ai_id, 5),
                control=PluginControlClient(bus, ("mcp", "extension-host")),
            )
    finally:
        await extension.close()
        await mcp_host.close()
        await bus.close()


PLAN = ResponsePlan(speech=[Speech(text="你好", delivery="text")],
                    emotion=Emotion(name="happy", intensity=0.5), actions=[])
OUTPUTS = (
    PLAN,
    ParticipationDecision(participate=True, reason="收到明确提问"),
    GroupRepeatDecision(repeat=False, reason="当前话题适合旁听"),
    ImageDescription(description="一张照片", image_type="photo", tags=[], match_quality=0,
                     emotion="neutral", sticker_description=""),
    StickerDecision(image_type="sticker", suitable=True, reason="适合表达感谢"),
    MemoryExtractionOutput(episode_summary="讨论了排查方法", memories=[]),
    MemoryConsolidationOutput(markdown="# 自我长期认知\n\n## 交流方式\n自然表达。"),
)


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("output", OUTPUTS, ids=lambda value: type(value).__name__)
async def test_model_tool_call_crosses_gateway_and_real_mcp_http(output_service, output, encoded):
    from shared.langchain_structured_output import parsed_output, structured_output_runnable

    message = tool_call(output)
    if encoded:
        message.tool_calls[0]["args"]["result"] = output.model_dump_json()
    model = ScriptedToolModel(responses=[message])
    runnable = structured_output_runnable(model, type(output), 1, output_service.client)
    result = await runnable.ainvoke([HumanMessage(content="给出本轮结论")])
    assert parsed_output(result, type(output)) == output
    assert model.bindings[0][1]["tool_choice"] == output_tool(type(output)).name
    async with Client(output_service.url) as client:
        catalog = {item.name: item for item in (await client.list_tools()).tools}
    assert set(catalog) == {item.name for item in OUTPUT_TOOLS}
    assert catalog[output_tool(type(output)).name].output_schema
    assert await load_toolset(output_service.bus, "test-ai", output_service.settings.timeouts) == []


def chat(model, service, tools=()):
    return ChatAgent(
        model=model, model_name="test", tools=list(tools),
        output_policy=ResponseOutputPolicy(service.settings.llm.output_limits),
        max_requests=4, participation_max_requests=2, max_tokens=500, retry_count=1, tool_retry_count=0,
        observability=service.settings.observability, output_client=service.client,
    )


@pytest.mark.parametrize("encoded", [False, True])
async def test_chat_graph_uses_business_result_then_mcp_final_tool(output_service, encoded):
    async def lookup(query: str) -> str:
        return "已核实资料"

    final_call = tool_call(PLAN)
    if encoded:
        final_call.tool_calls[0]["args"]["result"] = PLAN.model_dump_json()
    model = ScriptedToolModel(responses=[
        AIMessage(content="", tool_calls=[{"id": "lookup", "name": "lookup", "args": {"query": "资料"}}]),
        final_call,
    ])
    agent = chat(model, output_service, [StructuredTool.from_function(coroutine=lookup, description="查询资料")])
    assert await agent.generate_plan("结果通过 submit_response_plan 提交", "你好") == PLAN
    assert len(model.requests) == 2
    assert any(isinstance(item, ToolMessage) and item.content == "已核实资料" for item in model.requests[-1])


async def test_direct_reply_retries_invalid_model_call_and_requires_mcp(output_service):
    model = ScriptedToolModel(responses=[AIMessage(content='{"speech": []}'), tool_call(PLAN)])
    agent = chat(model, output_service)
    assert await agent.generate_plan("提交结论", "你好", allow_tools=False) == PLAN
    assert len(model.requests) == 2
    assert (await command(output_service.control, "disable", "structured-output", host="mcp"))["status"] == "completed"
    with pytest.raises(RemoteCallError):
        await output_service.client.submit(ResponsePlan, {"result": PLAN.model_dump()})
    assert (await command(output_service.control, "enable", "structured-output", host="mcp"))["status"] == "completed"
    assert await output_service.client.submit(ResponsePlan, {"result": PLAN.model_dump()}) == PLAN


async def test_mcp_rejects_invalid_shapes_and_gateway_enforces_ai_permission(output_service):
    async with Client(output_service.url) as client:
        result = await client.call_tool("submit_response_plan", {"result": {"speech": "bad"}})
        assert result.is_error
    with pytest.raises(RemoteCallError):
        await MCPOutputClient(output_service.bus, "unbound-ai", 5).submit(ResponsePlan, {"result": PLAN.model_dump()})


async def test_plain_text_graph_result_is_rejected(output_service):
    with pytest.raises(ValueError, match="MCP"):
        await chat(ScriptedToolModel(responses=[AIMessage(content="你好")]), output_service).generate_plan("提交结论", "你好")


@pytest.mark.parametrize("result", ['{"speech":"bad"}', "[]", "null", "invalid json"])
async def test_encoded_tool_arguments_keep_contract_validation(output_service, result):
    with pytest.raises(ValidationError):
        await output_service.client.submit(ResponsePlan, {"result": result})
