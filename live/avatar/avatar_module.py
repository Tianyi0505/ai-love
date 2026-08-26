from __future__ import annotations

import logging

from shared.contracts.avatar_command import AvatarCommand
from shared.nats_bus import Bus, Subscription

logger = logging.getLogger("ailove.avatar")

SUBJ_AVATAR = "avatar.command.{ai_id}"


class AvatarModule:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._subscription: Subscription | None = None

    async def start(self) -> None:
        self._subscription = await self._bus.subscribe_model(
            SUBJ_AVATAR.replace("{ai_id}", ">"),
            AvatarCommand,
            self._on_command,
        )

    async def stop(self) -> None:
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None

    async def _on_command(self, command: AvatarCommand) -> None:
        logger.info("[avatar] 指令: %s", command.type)
