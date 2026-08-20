from __future__ import annotations

from gateway.social_router import SocialRouter
from shared.configuration.global_settings import TimeoutSettings
from shared.contracts.rpc.relationship import RelationshipListRequest, RelationshipListResponse
from shared.contracts.rpc.social import CommentRequest, CommentResponse
from shared.infrastructure.nats_bus import Bus


class QZoneContextProvider:
    def __init__(
        self,
        account_id: str,
        router: SocialRouter,
        bus: Bus,
        timeouts: TimeoutSettings,
        priority_user_ids: frozenset[str],
    ) -> None:
        self._account_id = account_id
        self._router = router
        self._bus = bus
        self._timeouts = timeouts
        self._priority_user_ids = priority_user_ids

    async def relationship_profile(self, user_id: str) -> dict:
        ai_id = await self._router.owner_for(self._account_id)
        response = await self._bus.request_model(
            "relationship.list.request",
            RelationshipListRequest(ai_id=ai_id),
            RelationshipListResponse,
            timeout=self._timeouts.relationship_list_sec,
        )
        top_familiarity = max(record.familiarity for record in response.relationships)
        for record in response.relationships:
            if record.user_id == user_id:
                familiarity = record.familiarity
                if user_id in self._priority_user_ids:
                    familiarity = max(familiarity, top_familiarity)
                return {
                    "familiarity": familiarity,
                    "affinity": record.affinity,
                    "trust": record.trust,
                    "importance": record.importance,
                    "top_familiarity": top_familiarity,
                }
        raise LookupError(f"未找到联系人关系: {user_id}")

    async def generate_comment(
        self,
        feed_text: str,
        author_name: str,
        picture_urls: list[str],
    ) -> str:
        ai_id = await self._router.owner_for(self._account_id)
        response = await self._bus.request_model(
            "ai.comment.request",
            CommentRequest(
                ai_id=ai_id,
                account_id=self._account_id,
                feed_text=feed_text,
                author_name=author_name,
                picture_urls=picture_urls,
            ),
            CommentResponse,
            timeout=self._timeouts.comment_generation_sec,
        )
        return response.comment
