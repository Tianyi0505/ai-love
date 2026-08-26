from __future__ import annotations

import logging

from gateway.channel import Channel
from gateway.social_router import SocialRouter
from shared.identity_repository import IdentityRepository
from shared.relationship_repository import RelationshipRepository

logger = logging.getLogger("ailove.gateway.qq-whitelist")


class QQWhitelistSynchronizer:
    def __init__(
        self,
        channels: dict[str, Channel],
        account_adapters: dict[str, str],
        router: SocialRouter,
        identities: IdentityRepository,
        relationships: RelationshipRepository,
        user_ids: frozenset[str],
        ceiling_policy: str,
        contact_timeout_sec: float,
    ) -> None:
        self._channels = channels
        self._account_adapters = account_adapters
        self._router = router
        self._identities = identities
        self._relationships = relationships
        self._user_ids = user_ids
        self._ceiling_policy = ceiling_policy
        self._contact_timeout_sec = contact_timeout_sec

    async def sync(self) -> None:
        for account_id, adapter in self._account_adapters.items():
            if adapter != "qq":
                continue
            ai_id = await self._router.owner_for(account_id)
            if ai_id is None:
                raise LookupError(f"QQ 账号尚未绑定 AI: {account_id}")
            names = await self._channels[account_id].list_contacts(self._contact_timeout_sec)
            for user_id in self._user_ids:
                _, person_id = await self._identities.resolve_or_create(
                    "qq",
                    account_id,
                    user_id,
                    names[user_id],
                )
                await self._relationships.ensure_person(
                    ai_id,
                    person_id,
                    self._ceiling_policy,
                )
            logger.info("[gateway] 已同步 %s 个 QQ 白名单身份", len(self._user_ids))
