from __future__ import annotations

import logging

from services.ai_agent.events import live, social  # noqa: F401
from services.ai_agent.events.registry import event_registry

logger = logging.getLogger("ailove.ai-agent.events")


class EventHandlers:

    def __init__(self, service) -> None:
        self._service = service

    async def on_social(self, payload: bytes) -> None:
        handler = event_registry.get("social")
        await handler(self._service, payload)

    async def on_event(self, payload: bytes) -> None:
        handler = event_registry.get("live_event")
        await handler(self._service, payload)
