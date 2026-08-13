
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Protocol

from shared.contracts.agent import AgentDefinition
from shared.contracts.events import TurnRequest

logger = logging.getLogger("ailove.ai-agent.supervisor")


class Runtime(Protocol):
    definition: AgentDefinition

    async def start(self) -> None: ...
    async def handle_turn(self, turn: TurnRequest): ...
    async def handle_social(self, payload: bytes) -> None: ...
    async def handle_live(self, payload: bytes) -> None: ...
    async def handle_comment(self, payload: bytes) -> bytes: ...
    async def drain(self) -> None: ...
    async def stop(self) -> None: ...


RuntimeFactory = Callable[[AgentDefinition], Awaitable[Runtime]]


class AgentSupervisor:
    def __init__(self, runtime_factory: RuntimeFactory) -> None:
        self._runtime_factory = runtime_factory
        self._runtimes: dict[str, Runtime] = {}
        self._lock = asyncio.Lock()

    @property
    def ai_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._runtimes))

    async def reconcile(self, definitions: list[AgentDefinition]) -> None:
        desired = {definition.ai_id: definition for definition in definitions}
        async with self._lock:
            for ai_id, definition in desired.items():
                current = self._runtimes.get(ai_id)
                if current and current.definition.fingerprint == definition.fingerprint:
                    continue
                replacement = await self._runtime_factory(definition)
                await replacement.start()
                self._runtimes[ai_id] = replacement
                if current:
                    await current.drain()
                    await current.stop()
                    logger.info("[supervisor] AI 已热更新: %s v%s", ai_id, definition.version)
                else:
                    logger.info("[supervisor] AI 已加载: %s v%s", ai_id, definition.version)

            removed = set(self._runtimes) - set(desired)
            for ai_id in removed:
                runtime = self._runtimes.pop(ai_id)
                await runtime.drain()
                await runtime.stop()
                logger.info("[supervisor] AI 已卸载: %s", ai_id)

    async def dispatch(self, turn: TurnRequest):
        runtime = self._runtimes.get(turn.ai_id)
        if runtime is None:
            raise KeyError(f"AI 未激活: {turn.ai_id}")
        return await runtime.handle_turn(turn)

    async def dispatch_social(self, ai_id: str, payload: bytes) -> None:
        runtime = self._required(ai_id)
        await runtime.handle_social(payload)

    async def dispatch_live(self, ai_id: str, payload: bytes) -> None:
        runtime = self._required(ai_id)
        await runtime.handle_live(payload)

    async def dispatch_comment(self, ai_id: str, payload: bytes) -> bytes:
        runtime = self._required(ai_id)
        return await runtime.handle_comment(payload)

    def _required(self, ai_id: str) -> Runtime:
        runtime = self._runtimes.get(ai_id)
        if runtime is None:
            raise KeyError(f"AI 未激活: {ai_id}")
        return runtime

    async def stop(self) -> None:
        async with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            await runtime.drain()
            await runtime.stop()
