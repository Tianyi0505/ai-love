"""Exercise discovery from MCP through the extension bus to the next agent turn.

Only model execution and configuration storage are substituted; plugin lifecycles,
HTTP MCP discovery, permission filtering and typed bus codecs are the real ones.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plugin_fixtures import LocalBus
from test_plugin_runtime import command, manifest

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.response_plan import Emotion, ResponsePlan, Speech
from agent.extension_toolset_loader import load_toolset
from plugin_runtime.control import PluginControlClient
from plugin_runtime.host import PluginHost
from shared.global_settings import ObservabilitySettings, TimeoutSettings
from shared.service_settings import ExtensionHostSettings


async def test_next_agent_turn_tracks_mcp_enable_disable_and_server_removal(tmp_path):
    root = tmp_path / "catalog"
    manifest(
        root,
        "mcp.server",
        host="mcp",
        entrypoint="plugins.mcp:MCPServerPlugin",
        provides=("mcp.server",),
        config={"port": 0, "bind": "127.0.0.1"},
    )
    (root / "music").mkdir()
    (root / "music/plugin.json").write_bytes(
        (Path(__file__).parents[1] / "plugins/catalog/music/plugin.json").read_bytes()
    )
    manifest(
        root,
        "tools",
        host="extension-host",
        entrypoint="plugins.components:ServicePlugin",
        provides=("tools.gateway",),
        config={"implementation": "extensions.host.extension_host_service:ExtensionHostService"},
    )
    bus = LocalBus()
    mcp_host = PluginHost("mcp", bus=bus, roots=[root], state_directory=tmp_path / "state")
    await mcp_host.start()
    port = mcp_host.manager.resolve("mcp.server").http.servers[0].sockets[0].getsockname()[1]
    settings = ExtensionHostSettings(
        instance_addr="127.0.0.1:0",
        binding_poll_interval_sec=3600,
        grounding_timeout_sec=1,
        mcp_url=f"http://127.0.0.1:{port}/mcp",
        messages={},
    )
    configuration = SimpleNamespace(section=AsyncMock(return_value=settings), config_provider=SimpleNamespace(close=AsyncMock()))
    extension = PluginHost(
        "extension-host",
        bus=bus,
        roots=[root],
        state_directory=tmp_path / "state",
        configuration=AsyncMock(return_value=configuration),
    )
    control = PluginControlClient(bus, ("mcp", "extension-host"))
    timeouts = TimeoutSettings(**{key: 5 for key in TimeoutSettings.model_fields})
    from mcp import Client

    async with Client(settings.mcp_url) as client:
        music_name = (await client.list_tools()).tools[0].name
    definition = SimpleNamespace(
        ai_id="test-ai",
        fingerprint="fixed-config",
        extensions=[SimpleNamespace(enabled=True, permission="allow", tool_id=music_name, config={})],
    )
    observed_tools = []
    plan = ResponsePlan(
        speech=[Speech(text="你好", delivery="text")], emotion=Emotion(name="happy", intensity=0.5), actions=[]
    )

    def build_graph(**kwargs):
        names = [tool.name for tool in kwargs["tools"]]

        async def invoke(*args, **options):
            observed_tools.append(names)
            return {"structured_response": plan, "messages": []}

        return SimpleNamespace(ainvoke=invoke)

    async def current_tools():
        return await load_toolset(bus, "test-ai", timeouts)

    try:
        with (
            patch("extensions.host.extension_host_service.AgentDefinitionStore") as store,
            patch("agent.conversation.chat_agent.create_agent", side_effect=build_graph) as factory,
            patch("agent.conversation.chat_agent.structured_output_runnable"),
        ):
            store.return_value.list_active = AsyncMock(return_value=[definition])
            await extension.start()
            agent = ChatAgent(
                model=MagicMock(),
                model_name="test",
                tools=await current_tools(),
                output_policy=SimpleNamespace(validate_plan=lambda value: value),
                max_requests=4,
                participation_max_requests=1,
                max_tokens=100,
                retry_count=0,
                tool_retry_count=0,
                observability=ObservabilitySettings(
                    include_model_content=False, include_binary_content=False, include_model_request_parameters=False
                ),
                tool_loader=current_tools,
            )
            await agent.generate_plan("system", "first")
            await agent.generate_plan("system", "same catalog")
            assert factory.call_count == 1
            assert (await command(control, "disable", "music", host="mcp"))["status"] == "completed"
            await agent.generate_plan("system", "without music")
            assert (await command(control, "enable", "music", host="mcp"))["status"] == "completed"
            await agent.generate_plan("system", "music restored")
            assert (await command(control, "disable", "mcp.server", host="mcp", cascade=True))["status"] == "completed"
            await agent.generate_plan("system", "MCP offline")
            assert observed_tools == [[music_name], [music_name], [], [music_name], []]
            assert factory.call_count == 4
    finally:
        await extension.close()
        await mcp_host.close()
