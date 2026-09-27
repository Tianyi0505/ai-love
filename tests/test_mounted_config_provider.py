from __future__ import annotations

import asyncio
import json

import pytest
import yaml

from deploy.render_config import render
from shared.config_provider import ConfigurationError
from shared.mounted_config_provider import MountedConfigProvider, MountedConfigSettings, merge_config
from shared.service_config import ServiceConfig
from shared.service_settings import LiveEdgeSettings


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_projected_config_and_secret_updates_reconcile_and_unsubscribe(tmp_path):
    config, secrets = tmp_path / "config", tmp_path / "secrets"
    config.mkdir()
    secrets.mkdir()
    document = config / "service.live-edge.yaml"
    document.write_text(yaml.safe_dump({"instance_addr": "127.0.0.1:0", "obs_ws_url": "ws://localhost:4455"}))
    secret = secrets / document.name
    secret.write_text("stream_key: first\n")
    provider = MountedConfigProvider(
        MountedConfigSettings(directory=config, secret_directory=secrets, poll_interval_sec=0.01)
    )
    await provider.connect()
    snapshots = []

    async def changed(key, data):
        # Use the actual domain schema, including rejected replacement documents.
        snapshots.append(LiveEdgeSettings.model_validate(data))

    remove = await provider.watch("service.live-edge", changed)
    try:
        assert snapshots[-1].stream_key == "first"
        replacement = secrets / "replacement"
        replacement.write_text("stream_key: second\n")
        replacement.replace(secret)
        await until(lambda: snapshots[-1].stream_key == "second")
        document.write_text("obs_ws_url: [invalid yaml")
        await asyncio.sleep(0.03)
        assert snapshots[-1].stream_key == "second"
        document.write_text(yaml.safe_dump({"instance_addr": "127.0.0.1:1", "obs_ws_url": "ws://localhost:4455"}))
        await until(lambda: snapshots[-1].instance_addr == "127.0.0.1:1")
        await remove()
        previous = len(snapshots)
        secret.write_text("stream_key: after-unsubscribe\n")
        await asyncio.sleep(0.03)
        assert len(snapshots) == previous
    finally:
        await provider.close()


async def test_service_config_uses_mounted_provider_and_observes_hot_updates(tmp_path, monkeypatch):
    document = tmp_path / "service.live-edge.yaml"
    data = dict(instance_addr="127.0.0.1:0", obs_ws_url="ws://localhost:4455", stream_key="test")
    document.write_text(json.dumps(data))
    monkeypatch.setenv("AILOVE_CONFIG_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("AILOVE_CONFIG_POLL_INTERVAL_SEC", "0.01")
    monkeypatch.setenv("AILOVE_BUS_URL", "nats://127.0.0.1:4222")
    monkeypatch.setenv("AILOVE_CONFIG_RETRY_COUNT", "1")
    monkeypatch.setenv("AILOVE_CONFIG_RETRY_INTERVAL_SEC", "0.01")
    monkeypatch.setenv("AILOVE_SNOWFLAKE_WORKER_ID", "1")
    config = await ServiceConfig.load("live-edge")
    try:
        assert (await config.section(LiveEdgeSettings)).stream_key == "test"
        document.write_text(json.dumps({**data, "stream_key": "updated"}))
        await until(lambda: config._section["stream_key"] == "updated")
        assert (await config.section(LiveEdgeSettings)).stream_key == "updated"
    finally:
        await config.config_provider.close()


async def test_missing_mount_and_invalid_keys_fail_without_reading_outside_directory(tmp_path):
    missing = MountedConfigProvider(MountedConfigSettings(directory=tmp_path / "absent"))
    with pytest.raises(ConfigurationError, match="未挂载"):
        await missing.connect()
    provider = MountedConfigProvider(MountedConfigSettings(directory=tmp_path))
    await provider.connect()
    with pytest.raises(ConfigurationError, match="无效"):
        await provider.get("../private")
    with pytest.raises(ConfigurationError, match="不存在"):
        await provider.get("not-present")
    await provider.close()


def test_renderer_keeps_sensitive_values_out_of_configmap_and_preserves_merged_document():
    document = {
        "instance_addr": "127.0.0.1:0",
        "channels": [{"url": "ws://localhost:3001?access_token=private-value"}],
        "nested": {"stream_key": "private-stream", "normal": 12},
        "headers": {"Authorization": "private-header"},
    }
    configmap, secret = render({"service.example": document})
    public = configmap["data"]["service.example.yaml"]
    assert "private-" not in public
    assert (
        merge_config(yaml.safe_load(public), yaml.safe_load(secret["stringData"]["service.example.yaml"])) == document
    )
