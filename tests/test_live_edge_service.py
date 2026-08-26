from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from live.avatar.avatar_module import AvatarModule
from live.edge_service import LiveEdgeService
from live.stream.stream_module import StreamModule
from shared.contracts.avatar_command import AvatarCommand
from shared.contracts.stream_control import StreamControl
from shared.service_settings import LiveEdgeSettings


class LiveEdgeModuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_avatar_and_stream_share_bus_and_unsubscribe_on_stop(self) -> None:
        avatar_subscription = MagicMock()
        stream_subscription = MagicMock()
        bus = SimpleNamespace(
            subscribe_model=AsyncMock(
                side_effect=[avatar_subscription, stream_subscription]
            )
        )
        settings = LiveEdgeSettings(
            instance_addr="127.0.0.1:0",
            obs_ws_url="ws://127.0.0.1:4455",
            stream_key="stream-key",
        )
        avatar = AvatarModule(bus)
        stream = StreamModule(bus, settings)

        await avatar.start()
        await stream.start()
        await stream.stop()
        await avatar.stop()

        self.assertEqual(2, bus.subscribe_model.await_count)
        avatar_call, stream_call = bus.subscribe_model.await_args_list
        self.assertEqual("avatar.command.>", avatar_call.args[0])
        self.assertIs(AvatarCommand, avatar_call.args[1])
        self.assertEqual("obs.control", stream_call.args[0])
        self.assertIs(StreamControl, stream_call.args[1])
        avatar_subscription.unsubscribe.assert_called_once_with()
        stream_subscription.unsubscribe.assert_called_once_with()

    async def test_start_failure_stops_started_module(self) -> None:
        avatar_subscription = MagicMock()
        bus = SimpleNamespace(
            subscribe_model=AsyncMock(
                side_effect=[avatar_subscription, RuntimeError("stream failed")]
            )
        )
        cfg = SimpleNamespace(
            section=AsyncMock(
                return_value=LiveEdgeSettings(
                    instance_addr="127.0.0.1:0",
                    obs_ws_url="ws://127.0.0.1:4455",
                    stream_key="stream-key",
                )
            ),
            bus_url="nats://127.0.0.1:4222",
            bus_token=None,
        )
        service = LiveEdgeService(cfg, bus)

        with self.assertRaisesRegex(RuntimeError, "stream failed"):
            await service.on_start()

        avatar_subscription.unsubscribe.assert_called_once_with()


class LiveEdgeServiceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_owns_single_runtime_lifecycle(self) -> None:
        subscriptions = [MagicMock(), MagicMock()]
        bus = SimpleNamespace(
            connect=AsyncMock(),
            close=AsyncMock(),
            subscribe_model=AsyncMock(side_effect=subscriptions),
        )
        nacos = SimpleNamespace(register=AsyncMock(), close=AsyncMock())
        cfg = SimpleNamespace(
            section=AsyncMock(
                return_value=LiveEdgeSettings(
                    instance_addr="127.0.0.1:0",
                    obs_ws_url="ws://127.0.0.1:4455",
                    stream_key="stream-key",
                )
            ),
            nacos=nacos,
            bus_url="nats://127.0.0.1:4222",
            bus_token=None,
            instance_id="live-edge-1",
            instance_addr="127.0.0.1:0",
        )
        service = LiveEdgeService(cfg, bus)
        service.telemetry = MagicMock()

        await service.start()
        await service.stop()

        bus.connect.assert_awaited_once_with()
        nacos.register.assert_awaited_once_with(
            "live-edge", "live-edge-1", "127.0.0.1:0"
        )
        service.telemetry.start.assert_called_once_with()
        service.telemetry.stop.assert_called_once_with()
        self.assertEqual(2, bus.subscribe_model.await_count)
        for subscription in subscriptions:
            subscription.unsubscribe.assert_called_once_with()
        nacos.close.assert_awaited_once_with()
        bus.close.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
