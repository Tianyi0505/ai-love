from __future__ import annotations

import logging

from shared.contracts.stream_control import StreamControl
from shared.nats_bus import Bus, Subscription
from shared.service_settings import LiveEdgeSettings

logger = logging.getLogger("ailove.stream")

SUBJ_OBS_CONTROL = "obs.control"


class StreamModule:
    def __init__(self, bus: Bus, settings: LiveEdgeSettings) -> None:
        self._bus = bus
        self._obs_url = settings.obs_ws_url
        self._stream_key = settings.stream_key
        self._subscription: Subscription | None = None

    async def start(self) -> None:
        self._subscription = await self._bus.subscribe_model(
            SUBJ_OBS_CONTROL,
            StreamControl,
            self._on_control,
        )

    async def stop(self) -> None:
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None

    async def _on_control(self, command: StreamControl) -> None:
        logger.info("[stream] 控制: %s", command.action)
