from __future__ import annotations

import time

from gateway.channel import Channel
from shared.contracts.social import SocialMessage
from shared.entity_grounding_facade import EntityGroundingFacade
from shared.identity_repository import IdentityRepository


class GroupMemberSynchronizer:
    def __init__(
        self,
        channels: dict[str, Channel],
        identities: IdentityRepository,
        grounding: EntityGroundingFacade,
        refresh_sec: float,
    ) -> None:
        self._channels = channels
        self._identities = identities
        self._grounding = grounding
        self._refresh_sec = refresh_sec
        self._last_sync_at: dict[tuple[str, str], float] = {}

    async def sync(self, message: SocialMessage) -> None:
        key = (message.account_id, message.chat.chat_id)
        now = time.monotonic()
        last_sync = self._last_sync_at.get(key)
        if last_sync is not None and now - last_sync < self._refresh_sec:
            return

        members = await self._channels[message.account_id].list_group_members(message.chat.chat_id)
        if not members:
            return
        identities = await self._identities.resolve_or_create_many(
            message.platform,
            message.account_id,
            members,
        )
        snapshot = [
            {
                **member,
                "person_id": identities[str(member["platform_user_id"])][1],
            }
            for member in members
        ]
        await self._grounding.sync_group_members(
            message.platform,
            message.account_id,
            message.chat.chat_id,
            snapshot,
        )
        self._last_sync_at[key] = now
