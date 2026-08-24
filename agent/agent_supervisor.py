from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Protocol

from shared.contracts.agent import AgentDefinition
from shared.contracts.events import TurnRequest
from shared.contracts.live import InteractionEvent
from shared.contracts.rpc.social import CommentRequest, CommentResponse
from shared.contracts.social import SocialMessage

logger = logging.getLogger("ailove.ai-agent.supervisor")


# 定义运行时接口
class Runtime(Protocol):
    definition: AgentDefinition

    # 启动服务
    async def start(self) -> None: ...
    # 处理轮次
    async def handle_turn(self, turn: TurnRequest): ...
    # 处理社交
    async def handle_social(self, message: SocialMessage) -> None: ...
    # 处理直播
    async def handle_live(self, event: InteractionEvent) -> None: ...
    # 处理评论
    async def handle_comment(self, request: CommentRequest) -> CommentResponse: ...
    # 等待在途任务完成
    async def drain(self) -> None: ...
    # 停止服务
    async def stop(self) -> None: ...


RuntimeFactory = Callable[[AgentDefinition], Awaitable[Runtime]]


# 管理多个智能体运行实例
class AgentSupervisor:
    # 初始化当前实例
    def __init__(self, runtime_factory: RuntimeFactory) -> None:
        self._runtime_factory = runtime_factory
        self._runtimes: dict[str, Runtime] = {}
        self._lock = asyncio.Lock()

    # 列出智能体标识
    @property
    def ai_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._runtimes))

    # 同步智能体运行实例
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

    # 分发请求
    async def dispatch(self, turn: TurnRequest):
        runtime = self._runtimes.get(turn.ai_id)
        if runtime is None:
            raise KeyError(f"AI 未激活: {turn.ai_id}")
        return await runtime.handle_turn(turn)

    # 分发社交
    async def dispatch_social(self, ai_id: str, message: SocialMessage) -> None:
        runtime = self._required(ai_id)
        await runtime.handle_social(message)

    # 分发直播
    async def dispatch_live(self, ai_id: str, event: InteractionEvent) -> None:
        runtime = self._required(ai_id)
        await runtime.handle_live(event)

    # 分发评论
    async def dispatch_comment(self, ai_id: str, request: CommentRequest) -> CommentResponse:
        runtime = self._required(ai_id)
        return await runtime.handle_comment(request)

    # 读取必填配置
    def _required(self, ai_id: str) -> Runtime:
        runtime = self._runtimes.get(ai_id)
        if runtime is None:
            raise KeyError(f"AI 未激活: {ai_id}")
        return runtime

    # 停止服务
    async def stop(self) -> None:
        async with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            await runtime.drain()
            await runtime.stop()
