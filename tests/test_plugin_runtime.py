from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from plugin_fixtures import LocalBus

from admin.console.backend.plugins.router import router
from plugin_runtime.contracts import PluginCommand, PluginError
from plugin_runtime.control import PluginControlClient
from plugin_runtime.host import HostFileLock, PluginHost
from shared.nats_bus import create_bus


def manifest(
    root,
    plugin_id="echo",
    *,
    entrypoint="plugin_fixtures:EchoPlugin",
    provides=("echo",),
    requires=(),
    enabled=True,
    host="test",
    config=None,
):
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    data = dict(
        id=plugin_id,
        name=plugin_id,
        description="integration fixture",
        host=host,
        entrypoint=entrypoint,
        provides=provides,
        requires=requires,
        enabled=enabled,
        config=config or {},
    )
    (directory / "plugin.json").write_text(json.dumps(data), encoding="utf-8")


async def wait_operation(client, operation_id, host="test"):
    async with asyncio.timeout(10):
        while True:
            result = await client.call(host, "operation", operation_id=operation_id)
            if result["status"] not in {"accepted", "running"}:
                return result
            await asyncio.sleep(0.01)


async def command(client, action, plugin_id="echo", *, host="test", cascade=False, operation_id=None):
    from uuid import uuid4

    snapshot = await client.call(host, "list")
    payload = PluginCommand(
        operation_id=operation_id or uuid4().hex,
        plugin_id=plugin_id,
        action=action,
        expected_revision=snapshot["revision"],
        stop_dependents=cascade,
    ).model_dump()
    await client.call(host, "submit", command=payload)
    return await wait_operation(client, payload["operation_id"], host)


@pytest.fixture
async def running_host(tmp_path):
    root = tmp_path / "catalog"
    manifest(root)
    bus = LocalBus()
    host = PluginHost("test", bus=bus, roots=[root], state_directory=tmp_path / "state")
    await host.start()
    client = PluginControlClient(bus, ("test",))
    try:
        yield host, client, root
    finally:
        await host.close()


async def test_real_host_control_business_call_disable_install_enable_and_recovery(tmp_path):
    root = tmp_path / "catalog"
    manifest(root)
    state = tmp_path / "state"
    host = PluginHost("test", bus=LocalBus(), roots=[root], state_directory=state)
    await host.start()
    client = PluginControlClient(host.bus, ("test",))
    assert await host.bus.request("test.echo", b"hello", 1) == b"hello"
    assert (await command(client, "remove"))["status"] == "completed"
    with pytest.raises(RuntimeError, match="no responders"):
        await host.bus.request("test.echo", b"hello", 1)
    assert len(host.scheduler.get_jobs()) == 0
    await host.close()
    host = PluginHost("test", bus=LocalBus(), roots=[root], state_directory=state)
    await host.start()
    try:
        client = PluginControlClient(host.bus, ("test",))
        assert not (await client.call("test", "list"))["plugins"][0]["installed"]
        assert (await command(client, "install"))["status"] == "completed"
        assert (await command(client, "enable"))["status"] == "completed"
        assert await host.bus.request("test.echo", b"again", 1) == b"again"
        assert len(host.scheduler.get_jobs()) == 1
    finally:
        await host.close()


async def test_dependency_preflight_and_cascade_through_control(running_host):
    host, client, root = running_host
    manifest(root, "consumer", entrypoint="plugin_fixtures:DependentPlugin", provides=("consumer",), requires=("echo",))
    await client.call("test", "refresh")
    await command(client, "install", "consumer")
    await command(client, "enable", "consumer")
    with pytest.raises(PluginError, match="consumer"):
        await command(client, "disable")
    result = await command(client, "disable", cascade=True)
    assert result["status"] == "completed"
    assert all(plugin["state"] == "disabled" for plugin in (await client.call("test", "list"))["plugins"])
    assert (await command(client, "enable", "consumer"))["status"] == "completed"
    assert all(plugin["state"] == "active" for plugin in (await client.call("test", "list"))["plugins"])


async def test_disable_fences_new_calls_and_drains_the_real_request(running_host):
    host, client, _ = running_host
    host.manager.ports.update(entered=asyncio.Event(), release=asyncio.Event())
    work = asyncio.create_task(host.bus.request("test.echo", b"slow", 5))
    await host.manager.ports["entered"].wait()
    operation = asyncio.create_task(command(client, "disable"))
    await asyncio.sleep(0.03)
    assert not operation.done()
    with pytest.raises(RuntimeError, match="no responders"):
        await host.bus.request("test.echo", b"new", 1)
    host.manager.ports["release"].set()
    assert await work == b"slow"
    assert (await operation)["status"] == "completed"


async def test_idempotency_revision_conflict_and_failed_start_cleanup(running_host):
    host, client, root = running_host
    payload = dict(operation_id="same-operation", plugin_id="echo", action="disable", expected_revision=0)
    await client.call("test", "submit", command=payload)
    await wait_operation(client, "same-operation")
    replay = await client.call("test", "submit", command=payload)
    assert replay["status"] == "completed"
    with pytest.raises(PluginError, match="另一请求"):
        await client.call("test", "submit", command={**payload, "action": "enable"})
    with pytest.raises(PluginError, match="刷新"):
        await client.call("test", "submit", command={**payload, "operation_id": "stale-revision"})
    manifest(root, "broken", entrypoint="plugin_fixtures:FailStartPlugin", provides=())
    await client.call("test", "refresh")
    await command(client, "install", "broken")
    result = await command(client, "enable", "broken")
    assert result["status"] == "failed"
    assert "secret-value" not in json.dumps(await client.call("test", "list"))
    assert not host.bus.handlers["test.failed"]
    assert (await command(client, "enable"))["status"] == "completed"


async def test_failed_removal_can_be_retried_without_losing_resource_ownership(tmp_path):
    root = tmp_path / "catalog"
    manifest(root, entrypoint="plugin_fixtures:FailStopOncePlugin")
    host = PluginHost("test", bus=LocalBus(), roots=[root], state_directory=tmp_path / "state")
    await host.start()
    try:
        client = PluginControlClient(host.bus, ("test",))
        assert (await command(client, "remove"))["status"] == "failed"
        plugin = (await client.call("test", "list"))["plugins"][0]
        assert plugin["installed"] and plugin["state"] == "failed"
        assert (await command(client, "remove"))["status"] == "completed"
    finally:
        await host.close()


async def test_http_session_origin_preflight_and_operation_use_same_runtime(running_host):
    host, control, _ = running_host
    app = FastAPI()
    app.state.plugin_control = control
    app.state.session_store = type(
        "Sessions", (), {"exists": lambda self, token: asyncio.sleep(0, result=token == "valid")}
    )()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://panel.local") as client:
        assert (await client.get("/ai-love-api/plugins")).status_code == 401
        client.cookies.set("ai_love_session", "valid")
        snapshot = (await client.get("/ai-love-api/plugins")).json()
        assert snapshot["hosts"][0]["plugins"][0]["state"] == "active"
        payload = dict(
            host="test", plugin_id="echo", action="disable", operation_id="http-disable", expected_revision=0
        )
        assert (
            await client.post(
                "/ai-love-api/plugins/operations", json=payload, headers={"origin": "http://attacker.local"}
            )
        ).status_code == 403
        assert (await client.post("/ai-love-api/plugins/preflight", json=payload)).json()["allowed"]
        assert (await client.post("/ai-love-api/plugins/operations", json=payload)).status_code == 202
        assert (await wait_operation(control, "http-disable"))["status"] == "completed"
        assert not host.bus.handlers["test.echo"]


async def test_zero_plugins_never_import_business_packages(tmp_path):
    source = """
import asyncio, sys
from pathlib import Path
from plugin_runtime.host import PluginHost
from plugin_fixtures import LocalBus
async def run():
    host = PluginHost('empty', bus=LocalBus(), roots=[Path(sys.argv[1])], state_directory=Path(sys.argv[2]))
    await host.start()
    assert host.manager.snapshot()['plugins'] == []
    assert not any(name.split('.')[0] in {'agent', 'gateway', 'memory', 'gptsovits', 'plugins'} for name in sys.modules)
    await host.close()
asyncio.run(run())
"""
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    result = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path / "empty"), str(tmp_path / "state")],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr


def test_duplicate_host_cannot_mutate_same_journal(tmp_path):
    first, second = HostFileLock(tmp_path / "host.lock"), HostFileLock(tmp_path / "host.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="重复启动"):
            second.acquire()
    finally:
        first.close()
    second.acquire()
    second.close()


async def test_real_nats_builtin_avatar_can_hotplug_100_times(tmp_path):
    url = os.environ.get("AILOVE_TEST_NATS_URL")
    if not url:
        pytest.skip("真实 NATS 集成需要 AILOVE_TEST_NATS_URL")
    root = tmp_path / "catalog"
    builtin = Path(__file__).parents[1] / "plugins/catalog/avatar/plugin.json"
    (root / "avatar").mkdir(parents=True)
    data = json.loads(builtin.read_text())
    data["host"] = "live-edge-tests"
    (root / "avatar/plugin.json").write_text(json.dumps(data), encoding="utf-8")
    bus = create_bus(url, None)
    host = PluginHost("live-edge-tests", bus=bus, roots=[root], state_directory=tmp_path / "state")
    await host.start()
    control = PluginControlClient(create_bus(url, None), ("live-edge-tests",))
    try:
        assert len(bus._conn._subs) == 2  # management + the real AvatarModule subscription
        for _ in range(100):
            assert (await command(control, "disable", "avatar", host="live-edge-tests"))["status"] == "completed"
            assert len(bus._conn._subs) == 1
            assert (await command(control, "enable", "avatar", host="live-edge-tests"))["status"] == "completed"
            assert len(bus._conn._subs) == 2
    finally:
        await control.close()
        await host.close()


async def test_builtin_mcp_tools_disappear_and_return_through_real_http(tmp_path):
    from mcp import Client

    root = tmp_path / "catalog"
    manifest(
        root,
        "mcp.server",
        host="mcp",
        entrypoint="plugins.mcp:MCPServerPlugin",
        provides=("mcp.server",),
        config={"port": 0, "bind": "127.0.0.1"},
    )
    builtin = Path(__file__).parents[1] / "plugins/catalog/music/plugin.json"
    (root / "music").mkdir(parents=True)
    (root / "music/plugin.json").write_bytes(builtin.read_bytes())
    host = PluginHost("mcp", bus=LocalBus(), roots=[root], state_directory=tmp_path / "state")
    await host.start()
    control = PluginControlClient(host.bus, ("mcp",))
    try:
        port = host.manager.resolve("mcp.server").http.servers[0].sockets[0].getsockname()[1]
        async with Client(f"http://127.0.0.1:{port}/mcp") as mcp:
            tools = await mcp.list_tools()
            assert len(tools.tools) == 1
            name = tools.tools[0].name
            # The existing music adapter records intents; this does not contact a player.
            result = await mcp.call_tool(name, {"action": "pause"})
            assert not result.is_error
            assert (await command(control, "disable", "music", host="mcp"))["status"] == "completed"
            assert not (await mcp.list_tools()).tools
            assert (await mcp.call_tool(name, {"action": "pause"})).is_error
            assert (await command(control, "enable", "music", host="mcp"))["status"] == "completed"
            assert len((await mcp.list_tools()).tools) == 1
    finally:
        await host.close()


async def test_missing_and_cyclic_dependencies_are_rejected_before_import(tmp_path):
    root = tmp_path / "catalog"
    manifest(
        root, "first", entrypoint="does_not_exist:Plugin", requires=("second",), provides=("first",), enabled=False
    )
    manifest(
        root, "second", entrypoint="does_not_exist:Plugin", requires=("first",), provides=("second",), enabled=False
    )
    manifest(root, "missing", entrypoint="does_not_exist:Plugin", requires=("absent",), provides=(), enabled=False)
    host = PluginHost("test", bus=LocalBus(), roots=[root], state_directory=tmp_path / "state")
    await host.start()
    try:
        control = PluginControlClient(host.bus, ("test",))
        with pytest.raises(PluginError, match="成环"):
            await command(control, "enable", "first")
        with pytest.raises(PluginError, match="唯一"):
            await command(control, "enable", "missing")
        assert "does_not_exist" not in sys.modules
    finally:
        await host.close()


async def test_new_example_is_discovered_without_auto_install_and_invalid_catalog_is_isolated(tmp_path):
    root = tmp_path / "catalog"
    root.mkdir()
    host = PluginHost("live-edge", bus=LocalBus(), roots=[root], state_directory=tmp_path / "state")
    await host.start()
    client = PluginControlClient(host.bus, ("live-edge",))
    try:
        original = await client.call("live-edge", "list")
        (root / "broken").mkdir()
        (root / "broken/plugin.json").write_text("{invalid", encoding="utf-8")
        (root / "echo").mkdir()
        (root / "echo/plugin.json").write_bytes(
            (Path(__file__).parents[1] / "examples/plugin-catalog/echo/plugin.json").read_bytes()
        )
        snapshot = await client.call("live-edge", "refresh")
        assert snapshot["revision"] > original["revision"]
        assert snapshot["catalog_errors"][0]["source"] == "broken"
        assert not snapshot["plugins"][0]["installed"]
        assert not snapshot["plugins"][0]["enabled"]
        for action in ("install", "enable"):
            result = await command(client, action, "example.echo", host="live-edge")
            assert result["status"] == "completed"
        assert await host.bus.request("example.echo", b"delivered-plugin", 1) == b"delivered-plugin"
        assert (await command(client, "remove", "example.echo", host="live-edge"))["status"] == "completed"
        assert not host.bus.handlers["example.echo"]
    finally:
        await host.close()
