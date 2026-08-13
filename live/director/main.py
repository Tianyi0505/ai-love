
from __future__ import annotations

import asyncio
import json
import logging

from shared.contracts.live import InteractionEvent
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.service import BaseService
from live.director.policy import DeterministicDirectorPolicy

logger = logging.getLogger("ailove.director")

SUBJ_SPEECH = "ai.speech.request"
SUBJ_LIVE_EVENTS = "live.events"
SUBJ_LIVE_TURN = "agent.live.{ai_id}"


class DirectorService(BaseService):
    name = "director"

    async def on_start(self) -> None:
        section = await self.cfg.section()
        self._session_id = section["session_id"]
        self._director_cfg = await self.cfg.director(self._session_id)
        self._actors = [a["ai_id"] for a in self._director_cfg["actors"]]
        self._policy = DeterministicDirectorPolicy(self._actors)

        await self.bus.subscribe(SUBJ_LIVE_EVENTS, self._on_interaction)

        self.spawn(self._proactive_loop())

    async def on_stop(self) -> None:
        pass

    async def _on_interaction(self, payload: bytes) -> None:
        evt = InteractionEvent.from_dict(json.loads(payload))
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
        await self.bus.publish_json(SUBJ_LIVE_TURN.format(ai_id=ai_id), evt.to_dict())
        logger.info("[director] 互动已分配: %s -> %s", evt.type.value, ai_id)

    async def _proactive_loop(self) -> None:
        interval = self._director_cfg["proactive_interval_sec"]
        while True:
            await asyncio.sleep(interval)
            # 向 AI 请求自由发言内容
            logger.info("[director] 主动发言机会触发")


def main() -> None:
    async def run() -> None:
        svc = DirectorService(await ServiceConfig.load("director"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
