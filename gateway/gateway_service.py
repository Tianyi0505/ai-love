from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import datetime, timezone

import httpx
from stevedore.driver import DriverManager
from stevedore.extension import error_on_conflict

from gateway.channel import Channel
from gateway.gateway_message_handler import GatewayMessageHandler
from gateway.grounding_request_handler import GroundingRequestHandler
from gateway.group_member_synchronizer import GroupMemberSynchronizer
from gateway.qq_whitelist_synchronizer import QQWhitelistSynchronizer
from gateway.qzone_commented_feed_repository import QZoneCommentedFeedRepository
from gateway.qzone_context_provider import QZoneContextProvider
from gateway.qzone_service import QZoneService
from gateway.social_router import SocialRouter
from gateway.social_send_handler import SocialSendHandler
from shared import private_reply_observability as private_metrics
from shared.account_ownership_repository import AccountOwnershipRepository
from shared.agent_definition_store import AgentDefinitionStore
from shared.base_service import BaseService
from shared.contracts.behavior import BehaviorSchedule
from shared.contracts.rpc.grounding import (
    ResolvePeopleRequest,
    ResolvePeopleResponse,
    SearchGroupHistoryRequest,
    SearchGroupHistoryResponse,
)
from shared.contracts.rpc.social import (
    SocialSendRequest,
    SocialSendResponse,
    SocialSendStatusRequest,
    SocialSendStatusResponse,
)
from shared.contracts.social import SUBJ_SOCIAL_SEND
from shared.conversation_repository import ConversationRepository
from shared.database import Database
from shared.entity_grounding_facade import EntityGroundingFacade
from shared.global_settings import GlobalSettings
from shared.global_settings_store import GlobalSettingsStore
from shared.identity_repository import IdentityRepository
from shared.lfu import LazyLFU, LFUConfig
from shared.private_interaction_repository import PrivateInteractionRepository
from shared.relationship_repository import RelationshipRepository
from shared.service_config import ServiceConfig
from shared.service_settings import GatewaySettings
from shared.social_delivery_repository import SocialDeliveryRepository

logger = logging.getLogger("ailove.gateway")


class GatewayService(BaseService):
    name = "gateway"

    async def on_start(self) -> None:
        self._cleanup = AsyncExitStack()
        section = await self.cfg.section(GatewaySettings)
        settings = await GlobalSettingsStore(self.cfg.config_provider).load()
        self._http_client = httpx.AsyncClient()
        self._cleanup.push_async_callback(self._http_client.aclose)
        self._db = Database()
        self._cleanup.push_async_callback(self._db.close)
        await self._db.connect()

        router = SocialRouter(AccountOwnershipRepository(self._db))
        identities = IdentityRepository(self._db)
        relationships = RelationshipRepository(self._db, settings.relationship_storage)
        conversations = ConversationRepository(self._db, settings.social.message_retention_days)
        private_jobs = PrivateInteractionRepository(self._db, retention_days=settings.social.message_retention_days)
        deliveries = SocialDeliveryRepository(self._db)
        grounding = EntityGroundingFacade(
            self._db,
            settings.grounding,
            LazyLFU(LFUConfig(**settings.lfu.evidence.model_dump())),
        )
        priority_user_ids = frozenset(str(user_id) for user_id in settings.qq.whitelist)

        self._channels: dict[str, Channel] = {}
        account_configs: dict[str, dict] = {}
        account_adapters = {spec.account_id: spec.adapter for spec in section.accounts}
        group_members = GroupMemberSynchronizer(
            self._channels,
            identities,
            grounding,
            settings.qq.group_member_refresh_sec,
        )
        grounding_requests = GroundingRequestHandler(grounding, router, settings.grounding)
        message_handler = GatewayMessageHandler(
            channels=self._channels,
            identities=identities,
            conversations=conversations,
            router=router,
            group_members=group_members,
            grounding=grounding_requests,
            bus=self.bus,
            live_settings=settings.live,
            priority_user_ids=priority_user_ids,
            private_jobs=private_jobs,
            self_user_ids={spec.account_id: str(spec.config.get("uin", "")) for spec in section.accounts},
        )
        social_sender = SocialSendHandler(self._channels, conversations, deliveries, router,
                                         send_retries=section.private_reply.send_retries)

        for spec in section.accounts:
            channel_config = {**spec.config, "account_id": spec.account_id}
            if spec.adapter == "qq":
                channel_config.update(
                    message_timeout_sec=settings.timeouts.qq_message_sec,
                    forward_timeout_sec=settings.timeouts.qq_forward_sec,
                )
            context = getattr(self, "plugin_context", None)
            channel = context.require("platform.channels").create(
                spec.adapter, channel_config, self._http_client,
            ) if context else DriverManager(
                namespace="ai_love.channels",
                name=spec.adapter,
                invoke_on_load=True,
                invoke_args=(channel_config, self._http_client),
                conflict_resolver=error_on_conflict,
            ).driver
            channel.set_message_handler(message_handler.handle)
            if context:
                context.resources.on_quiesce(channel.stop)
            self._channels[spec.account_id] = channel
            account_configs[spec.account_id] = channel_config
            self.spawn(channel.start())

        await QQWhitelistSynchronizer(
            self._channels,
            account_adapters,
            router,
            identities,
            relationships,
            priority_user_ids,
            settings.relationship_storage.whitelist_ceiling_policy,
            settings.timeouts.friend_list_sec,
        ).sync()

        await self.bus.reply_model(
            SUBJ_SOCIAL_SEND,
            SocialSendRequest,
            SocialSendResponse,
            social_sender.send,
        )
        await self.bus.reply_model("social.send.status.request", SocialSendStatusRequest,
                                   SocialSendStatusResponse, social_sender.status)

        async def recover_private():
            try:
                await message_handler.recover_private(section.private_reply.batch_size)
            except Exception as exc:
                private_metrics.scan_failure("gateway-inbound", type(exc).__name__)
            try:
                await social_sender.recover()
            except Exception as exc:
                private_metrics.scan_failure("gateway-delivery", type(exc).__name__)

        self.scheduler.add_job(recover_private, "interval", seconds=section.private_reply.scan_interval_sec,
                               max_instances=1)
        self.scheduler.add_job(private_jobs.cleanup, "interval", hours=24, max_instances=1)
        self.scheduler.add_job(deliveries.cleanup, "interval", hours=24, max_instances=1)
        await self.bus.reply_model(
            "identity.resolve-people.request",
            ResolvePeopleRequest,
            ResolvePeopleResponse,
            grounding_requests.resolve_people,
        )
        await self.bus.reply_model(
            "history.search-group.request",
            SearchGroupHistoryRequest,
            SearchGroupHistoryResponse,
            grounding_requests.search_group_history,
        )

        qq_account_ids = [account_id for account_id, adapter in account_adapters.items() if adapter == "qq"]
        if qq_account_ids:
            await self._schedule_qzone(
                qq_account_ids[0],
                account_configs[qq_account_ids[0]],
                router,
                settings,
            )

    async def on_stop(self) -> None:
        for channel in getattr(self, "_channels", {}).values():
            await channel.stop()
        if hasattr(self, "_cleanup"):
            await self._cleanup.aclose()

    async def _schedule_qzone(
        self,
        account_id: str,
        account_config: dict,
        router: SocialRouter,
        settings: GlobalSettings,
    ) -> None:
        owner_ai_id = await router.owner_for(account_id)
        if owner_ai_id is None:
            raise LookupError(f"QQ 账号尚未绑定 AI: {account_id}")
        definition = await AgentDefinitionStore(self.cfg.config_provider).load(owner_ai_id)
        proactive_schedule = BehaviorSchedule.from_config(definition.behavior_policy)
        context = QZoneContextProvider(
            account_id,
            router,
            self.bus,
            settings.timeouts,
            frozenset(str(user_id) for user_id in settings.qq.whitelist),
        )
        qzone = QZoneService(
            napcat_http_url=account_config["http_url"],
            qq_settings=settings.qq,
            qq_uin=account_config["uin"],
            relationship_provider=context.relationship_profile,
            comment_generator=context.generate_comment,
            proactive_allowed=proactive_schedule.allows_proactive,
            timeouts=settings.timeouts,
            http_client=self._http_client,
            commented_repo=QZoneCommentedFeedRepository(self._db, account_id),
        )
        self.scheduler.add_job(
            qzone.run_once,
            "interval",
            seconds=settings.qq.space_interval_sec,
            next_run_time=datetime.now(timezone.utc),
        )
        logger.info("[gateway] QQ空间定时任务已挂载")


def main() -> None:
    async def run() -> None:
        service = GatewayService(await ServiceConfig.load("gateway"))
        await service.start()
        await service.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
