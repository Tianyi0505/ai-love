
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from live.director.deterministic_director_policy import DeterministicDirectorPolicy
from shared.base_service import BaseService
from shared.contracts.live import InteractionEvent
from shared.service_config import ServiceConfig
from shared.service_settings import DirectorSessionSettings, DirectorSettings

logger = logging.getLogger("ailove.director")

SUBJ_SPEECH = "ai.speech.request"
SUBJ_LIVE_EVENTS = "live.events"
SUBJ_LIVE_TURN = "agent.live.{ai_id}"


# 提供导演服务能力
class DirectorService(BaseService):
    name = "director"

    # 启动服务
    async def on_start(self) -> None:
        section = await self.cfg.section(DirectorSettings)
        self._session_id = section.session_id
        self._director_cfg = await self.cfg.director(self._session_id, DirectorSessionSettings)
        self._actors = [actor.ai_id for actor in self._director_cfg.actors]
        self._policy = DeterministicDirectorPolicy(self._actors)

        await self.bus.subscribe_model(SUBJ_LIVE_EVENTS, InteractionEvent, self._on_interaction)

        self.scheduler.add_job(
            self._proactive_opportunity,
            "interval",
            seconds=self._director_cfg.proactive_interval_sec,
            next_run_time=datetime.now(timezone.utc),
        )

    # 停止服务
    async def on_stop(self) -> None:
        pass

    # 处理互动
    async def _on_interaction(self, evt: InteractionEvent) -> None:
        ai_id = self._policy.choose(evt)
        if not ai_id:
            logger.warning("[director] 直播场次没有可用 AI: %s", self._session_id)
            return
        evt.context_metadata = {
            **evt.context_metadata,
            "session_id": self._session_id,
            "target_ai_id": ai_id,
            "active_actors": list(self._policy.actors),
        }
        await self.bus.publish_model(SUBJ_LIVE_TURN.format(ai_id=ai_id), evt)
        logger.info("[director] 互动已分配: %s -> %s", evt.type.value, ai_id)

    # 触发主动交互机会
    async def _proactive_opportunity(self) -> None:
        logger.info("[director] 主动发言机会触发")


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = DirectorService(await ServiceConfig.load("director"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
