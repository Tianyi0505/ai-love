from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from redis.asyncio import Redis

from agent.agent_supervisor import AgentSupervisor
from agent.ai_runtime import AIRuntime
from shared.configuration.connection_settings import RedisConnectionSettings
from shared.configuration.service_settings import AIAgentSettings
from shared.contracts.live import InteractionEvent
from shared.contracts.rpc.social import CommentRequest, CommentResponse
from shared.contracts.social import SocialMessage
from shared.infrastructure.base_service import BaseService
from shared.infrastructure.database import Database
from shared.infrastructure.nacos_agent_definition_store import NacosAgentDefinitionStore
from shared.infrastructure.service_config import ServiceConfig
from shared.persistence.repositories.account_ownership_repository import AccountOwnershipRepository
from shared.persistence.repositories.ai_profile_repository import AIProfileRepository

logger = logging.getLogger("ailove.ai-agent")

SUBJ_SOCIAL_ALL = "social.chat.>"
SUBJ_LIVE_TURN_ALL = "agent.live.>"
SUBJ_COMMENT = "ai.comment.request"


# 提供AI智能体服务能力
class AIAgentService(BaseService):
    name = "ai-agent"

    @property
    def redis(self) -> Redis:
        return self._redis

    # 启动服务
    async def on_start(self) -> None:
        redis_settings = RedisConnectionSettings()
        self._redis = Redis.from_url(
            redis_settings.url,
            password=redis_settings.password,
            decode_responses=True,
        )
        await self._redis.ping()
        self._definitions = NacosAgentDefinitionStore(self.cfg.nacos)
        self._settings = await self.cfg.section(AIAgentSettings)
        self._db = Database()
        await self._db.connect()
        self._profiles = AIProfileRepository(self._db)
        self._accounts = AccountOwnershipRepository(self._db)

        # 创建智能体运行时
        async def runtime_factory(definition):
            account_ids = await self._account_ids_for(definition.ai_id)
            return AIRuntime(self, definition, account_ids)

        self._supervisor = AgentSupervisor(runtime_factory)
        await self._supervisor.reconcile(await self._active_definitions())

        await self.bus.subscribe_model(SUBJ_SOCIAL_ALL, SocialMessage, self._on_social)
        await self.bus.subscribe_model(SUBJ_LIVE_TURN_ALL, InteractionEvent, self._on_live)
        await self.bus.reply_model(SUBJ_COMMENT, CommentRequest, CommentResponse, self._on_comment)
        self.scheduler.add_job(
            self._refresh_catalog,
            "interval",
            seconds=self._settings.catalog_poll_interval_sec,
            next_run_time=datetime.now(timezone.utc),
        )
        await self._watch_agent_configs()

    # 停止服务
    async def on_stop(self) -> None:
        await self._supervisor.stop()
        await self._redis.aclose()
        await self._db.close()

    # 监听智能体配置变化
    async def _watch_agent_configs(self) -> None:

        # 重新加载配置
        async def _reload(_data_id: str, _parsed: dict) -> None:
            await self._supervisor.reconcile(await self._active_definitions())

        definitions = await self._active_definitions()
        for definition in definitions:
            await self.cfg.nacos.watch(f"agent.{definition.ai_id}", _reload)
        await self.cfg.nacos.watch("agent.default", _reload)
        await self.cfg.nacos.watch("agent.catalog", _reload)

    # 加载已启用的智能体定义
    async def _active_definitions(self):
        records = await self._profiles.list_active()
        return [await self._definitions.load(record.ai_id) for record in records]

    # 获取智能体绑定的账号标识
    async def _account_ids_for(self, ai_id: str) -> tuple[str, ...]:
        return tuple(await self._accounts.accounts_for_ai(ai_id))

    # 刷新智能体目录
    async def _refresh_catalog(self) -> None:
        await self._supervisor.reconcile(await self._active_definitions())

    # 处理社交
    async def _on_social(self, msg: SocialMessage) -> None:
        ai_id = str(msg.meta.get("ai_id", ""))
        if not ai_id:
            logger.warning("[ai-agent] 拒绝缺少 ai_id 的社交消息: account=%s", msg.account_id)
            return
        await self._supervisor.dispatch_social(ai_id, msg)

    # 处理直播
    async def _on_live(self, event: InteractionEvent) -> None:
        ai_id = str(event.context_metadata.get("target_ai_id", "") or event.ai_target)
        if not ai_id:
            logger.warning("[ai-agent] 拒绝未经直播导演分配的事件: %s", event.event_id)
            return
        await self._supervisor.dispatch_live(ai_id, event)

    # 处理评论
    async def _on_comment(self, request: CommentRequest) -> CommentResponse:
        return await self._supervisor.dispatch_comment(request.ai_id, request)


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        service = AIAgentService(await ServiceConfig.load("ai-agent"))
        await service.start()
        await service.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
