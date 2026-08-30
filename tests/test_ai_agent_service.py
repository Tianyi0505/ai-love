from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from agent.ai_agent_service import AIAgentService
from memory.memory_module import MemoryModule
from shared.service_settings import AIAgentSettings


class AIAgentServiceMemoryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_module_reuses_agent_resources_and_stops_after_runtimes(self) -> None:
        redis = SimpleNamespace(ping=AsyncMock(), aclose=AsyncMock())
        database = SimpleNamespace(connect=AsyncMock(), close=AsyncMock())
        definitions = MagicMock()
        profiles = SimpleNamespace(list_active=AsyncMock(return_value=[]))
        accounts = MagicMock()
        supervisor = SimpleNamespace(reconcile=AsyncMock(), stop=AsyncMock())
        memory_module = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
        nacos = SimpleNamespace(watch=AsyncMock())
        cfg = SimpleNamespace(
            nacos=nacos,
            section=AsyncMock(
                return_value=AIAgentSettings(
                    instance_addr="127.0.0.1:0",
                    catalog_poll_interval_sec=2,
                    account_ids_by_ai={},
                )
            ),
            bus_url="nats://127.0.0.1:4222",
            bus_token=None,
        )

        async def subscribe_after_memory_start(*_args) -> MagicMock:
            memory_module.start.assert_awaited_once_with()
            return MagicMock()

        bus = SimpleNamespace(
            subscribe_model=AsyncMock(side_effect=subscribe_after_memory_start),
            reply_model=AsyncMock(side_effect=subscribe_after_memory_start),
        )

        with (
            patch("agent.ai_agent_service.Redis") as redis_type,
            patch(
                "agent.ai_agent_service.RedisConnectionSettings",
                return_value=SimpleNamespace(
                    url="redis://127.0.0.1:6379/0",
                    password="test-password",
                ),
            ),
            patch("agent.ai_agent_service.Database", return_value=database),
            patch(
                "agent.ai_agent_service.NacosAgentDefinitionStore",
                return_value=definitions,
            ),
            patch("agent.ai_agent_service.AIProfileRepository", return_value=profiles),
            patch("agent.ai_agent_service.AccountOwnershipRepository", return_value=accounts),
            patch("agent.ai_agent_service.AgentSupervisor", return_value=supervisor),
            patch("agent.ai_agent_service.MemoryModule", return_value=memory_module) as memory_type,
        ):
            redis_type.from_url.return_value = redis
            service = AIAgentService(cfg, bus)

            await service.on_start()

            memory_type.assert_called_once_with(
                nacos=nacos,
                bus=bus,
                scheduler=service.scheduler,
                database=database,
                definitions=definitions,
            )
            database.connect.assert_awaited_once_with()
            memory_module.start.assert_awaited_once_with()
            supervisor.reconcile.assert_awaited_once_with([])

            lifecycle = MagicMock()
            lifecycle.attach_mock(supervisor.stop, "stop_runtimes")
            lifecycle.attach_mock(memory_module.stop, "stop_memory")
            lifecycle.attach_mock(redis.aclose, "close_redis")
            lifecycle.attach_mock(database.close, "close_database")

            await service.on_stop()

            self.assertEqual(
                [
                    call.stop_runtimes(),
                    call.stop_memory(),
                    call.close_redis(),
                    call.close_database(),
                ],
                lifecycle.mock_calls,
            )


class MemoryModuleLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_unsubscribes_all_shared_bus_handlers(self) -> None:
        first = MagicMock()
        second = MagicMock()
        module = MemoryModule(
            nacos=MagicMock(),
            bus=MagicMock(),
            scheduler=MagicMock(),
            database=MagicMock(),
            definitions=MagicMock(),
        )
        module._subscriptions.extend([first, second])

        await module.stop()

        first.unsubscribe.assert_called_once_with()
        second.unsubscribe.assert_called_once_with()
        self.assertEqual([], module._subscriptions)


if __name__ == "__main__":
    unittest.main()
