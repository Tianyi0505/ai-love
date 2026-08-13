
from __future__ import annotations

import asyncio
import json
import logging
import os

from shared.contracts.live import InteractionEvent
from shared.contracts.social import SocialMessage
from shared.infrastructure.agent_store import NacosAgentDefinitionStore
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.database import Database
from shared.infrastructure.repositories import AIProfileRepository, AccountOwnershipRepository
from shared.infrastructure.service import BaseService
from services.ai_agent.runtime import AIRuntime
from services.ai_agent.supervisor import AgentSupervisor

logger = logging.getLogger("ailove.ai-agent")

SUBJ_SOCIAL_ALL = "social.chat.>"
SUBJ_LIVE_TURN_ALL = "agent.live.>"
SUBJ_COMMENT = "ai.comment.request"


class AIAgentService(BaseService):
    name = "ai-agent"

    async def on_start(self) -> None:
        section = await self.cfg.section()
        self._definitions = NacosAgentDefinitionStore(self.cfg.nacos)
        self._fallback_accounts = {
            str(ai_id): tuple(str(account_id) for account_id in account_ids)
            for ai_id, account_ids in section["account_ids_by_ai"].items()
            if isinstance(account_ids, list)
        }
        self._db = None
        self._profiles = None
        self._accounts = None
        if os.environ.get("AILOVE_DATABASE_URL"):
            self._db = Database()
            await self._db.connect()
            self._profiles = AIProfileRepository(self._db)
            self._accounts = AccountOwnershipRepository(self._db)

        async def runtime_factory(definition):
            account_ids = await self._account_ids_for(definition.ai_id)
            return AIRuntime(self, definition, account_ids)

        self._supervisor = AgentSupervisor(runtime_factory)
        await self._supervisor.reconcile(await self._active_definitions())

        await self.bus.subscribe(SUBJ_SOCIAL_ALL, self._on_social)
        await self.bus.subscribe(SUBJ_LIVE_TURN_ALL, self._on_live)
        await self.bus.reply(SUBJ_COMMENT, self._on_comment)
        self.spawn(self._catalog_loop())
        await self._watch_agent_configs()

    async def on_stop(self) -> None:
        await self._supervisor.stop()
        if self._db is not None:
            await self._db.close()

    async def _watch_agent_configs(self) -> None:

        async def _reload(_data_id: str, _parsed: dict) -> None:
            try:
                await self._supervisor.reconcile(await self._active_definitions())
            except Exception as exc:
                logger.warning("[ai-agent] 配置热更新失败: %s", exc)

        definitions = await self._active_definitions()
        for definition in definitions:
            await self.cfg.nacos.watch(f"agent.{definition.ai_id}", _reload)
        await self.cfg.nacos.watch("agent.catalog", _reload)

    async def _active_definitions(self):
        if self._profiles is None:
            return await self._definitions.list_active()
        records = await self._profiles.list_active()
        return [await self._definitions.load(record.ai_id) for record in records]

    async def _account_ids_for(self, ai_id: str) -> tuple[str, ...]:
        if self._accounts is not None:
            return tuple(await self._accounts.accounts_for_ai(ai_id))
        return self._fallback_accounts.get(ai_id, ())

    async def _catalog_loop(self) -> None:
        poll_interval = float((await self.cfg.section())["catalog_poll_interval_sec"])
        while True:
            await asyncio.sleep(poll_interval)
            try:
                await self._supervisor.reconcile(await self._active_definitions())
            except Exception:
                logger.exception("[ai-agent] Catalog 更新失败，保留上一有效版本")

    async def _on_social(self, payload: bytes) -> None:
        msg = SocialMessage.from_dict(json.loads(payload))
        ai_id = str(msg.meta.get("ai_id", ""))
        if not ai_id:
            logger.warning("[ai-agent] 拒绝缺少 ai_id 的社交消息: account=%s", msg.account_id)
            return
        await self._supervisor.dispatch_social(ai_id, payload)

    async def _on_live(self, payload: bytes) -> None:
        event = InteractionEvent.from_dict(json.loads(payload))
        ai_id = str(event.context_metadata.get("target_ai_id", "") or event.ai_target)
        if not ai_id:
            logger.warning("[ai-agent] 拒绝未经直播导演分配的事件: %s", event.event_id)
            return
        await self._supervisor.dispatch_live(ai_id, payload)

    async def _on_comment(self, payload: bytes) -> bytes:
        request = json.loads(payload)
        ai_id = str(request.get("ai_id", ""))
        if not ai_id:
            return json.dumps({"comment": "", "error": "缺少 ai_id"}).encode()
        return await self._supervisor.dispatch_comment(ai_id, payload)


def main() -> None:
    async def run() -> None:
        service = AIAgentService(await ServiceConfig.load("ai-agent"))
        await service.start()
        await service.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
