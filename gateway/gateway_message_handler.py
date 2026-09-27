from __future__ import annotations

import logging

from gateway.channel import Channel
from gateway.grounding_request_handler import GroundingRequestHandler
from gateway.group_member_synchronizer import GroupMemberSynchronizer
from gateway.social_router import SocialRouter
from shared import private_reply_observability as private_metrics
from shared.contracts.live import InteractionEvent, InteractionType, Viewer
from shared.contracts.social import SUBJ_SOCIAL_CHAT, ChatType, SocialMessage
from shared.contracts.turn import new_run_id
from shared.conversation_repository import ConversationRepository
from shared.global_settings import LiveSettings
from shared.identity_repository import IdentityRepository
from shared.nats_bus import Bus

SUBJ_LIVE_EVENTS = "live.events"
logger = logging.getLogger("ailove.gateway.private")


class GatewayMessageHandler:
    def __init__(
        self,
        *,
        channels: dict[str, Channel],
        identities: IdentityRepository,
        conversations: ConversationRepository,
        router: SocialRouter,
        group_members: GroupMemberSynchronizer,
        grounding: GroundingRequestHandler,
        bus: Bus,
        live_settings: LiveSettings,
        priority_user_ids: frozenset[str],
        private_jobs,
        self_user_ids: dict[str, str] | None = None,
    ) -> None:
        self._channels = channels
        self._identities = identities
        self._conversations = conversations
        self._router = router
        self._group_members = group_members
        self._grounding = grounding
        self._bus = bus
        self._live_settings = live_settings
        self._priority_user_ids = priority_user_ids
        self._private_jobs = private_jobs
        self._self_user_ids = self_user_ids or {}

    async def handle(self, message: SocialMessage) -> None:
        if message.chat.chat_type == ChatType.PRIVATE:
            await self._handle_private(message)
            return
        message.meta["run_id"] = new_run_id()
        if message.platform == "qq":
            message.meta["priority_contact"] = str(message.sender.user_id) in self._priority_user_ids
        if message.chat.chat_type == ChatType.GROUP and message.chat.chat_id.startswith("live:"):
            await self._publish_live_interaction(message)
            return

        message = await self._channels[message.account_id].hydrate_message(message)
        identity_id, person_id = await self._identities.resolve_or_create(
            message.platform,
            message.account_id,
            message.sender.user_id,
            message.sender.name,
        )
        message.meta["platform_identity_id"] = identity_id
        message.meta["person_id"] = person_id
        message.meta["conversation_id"] = await self._conversations.get_or_create(
            message.platform,
            message.account_id,
            message.chat.chat_id,
            message.chat.chat_type.value,
        )
        turn = await self._router.route(message)
        message.meta["ai_id"] = turn.ai_id
        if message.chat.chat_type == ChatType.GROUP:
            await self._group_members.sync(message)
        message.meta["entity_context"] = await self._grounding.ground_message(message, turn.ai_id)
        await self._conversations.record_inbound(message, turn.ai_id)
        await self._bus.publish_model(SUBJ_SOCIAL_CHAT.format(ai_id=turn.ai_id), message)

    async def _handle_private(self, message):
        if not message.message_id or message.sender.user_id == self._self_user_ids.get(message.account_id):
            logger.info("private_rejected account_id=%s message_id=%s", message.account_id, message.message_id)
            return
        identity_id, person_id = await self._identities.resolve_or_create(
            message.platform, message.account_id, message.sender.user_id, message.sender.name)
        message.meta.update(platform_identity_id=identity_id, person_id=person_id)
        message.meta['conversation_id'] = await self._conversations.get_or_create(
            message.platform, message.account_id, message.chat.chat_id, message.chat.chat_type.value)
        turn = await self._router.route(message)
        message.meta.update(
            ai_id=turn.ai_id,
            priority_contact=message.sender.user_id in self._priority_user_ids,
        )
        job, fresh = await self._private_jobs.accept(message, turn.ai_id)
        private_metrics.received(duplicate=not fresh)
        if not fresh:
            return
        await self._prepare_private(job)

    async def _prepare_private(self, job):
        message = SocialMessage.model_validate(job.message_snapshot)
        message.meta.update(ai_id=job.ai_id, run_id=job.run_id, private_reply_job_id=str(job.job_id))
        try:
            message = await self._channels[message.account_id].hydrate_message(message)
            message.meta['entity_context'] = await self._grounding.ground_message(message, job.ai_id)
        except Exception as exc:
            message.meta['private_input_error'] = type(exc).__name__
            logger.warning('private_input_fallback run_id=%s', job.run_id)
        await self._conversations.record_inbound(message, job.ai_id)
        await self._private_jobs.ready(job.job_id, message)
        await self._bus.publish_model(SUBJ_SOCIAL_CHAT.format(ai_id=job.ai_id), message)

    async def recover_private(self, limit=100):
        jobs = await self._private_jobs.pending(('accepted',), limit)
        private_metrics.pending(jobs)
        for job in jobs:
            try:
                await self._prepare_private(job)
            except Exception as exc:
                logger.warning('private_prepare_pending run_id=%s reason=%s', job.run_id, type(exc).__name__)

    # 解析直播事件类型，未声明的类型返回 None 表示不接收
    @staticmethod
    def _interaction_type(raw: object) -> InteractionType | None:
        try:
            return InteractionType(raw)
        except ValueError:
            return None

    async def _publish_live_interaction(self, message: SocialMessage) -> None:
        interaction_type = self._interaction_type(message.meta.get("bili_type"))
        if interaction_type is None:
            return
        event = InteractionEvent(
            type=interaction_type,
            actor=Viewer(uid=int(message.sender.user_id), name=message.sender.name),
            importance=self._live_settings.default_importance,
            content=message.text,
            meta=message.meta,
            ai_target=message.at_user_id,
            context_metadata={"account_id": message.account_id},
        )
        await self._bus.publish_model(SUBJ_LIVE_EVENTS, event)
