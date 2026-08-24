from __future__ import annotations

import asyncio

import jieba

from memory.application.memory_cleanup_service import MemoryCleanupService
from memory.application.memory_query_handler import MemoryQueryHandler
from memory.application.relationship_handler import RelationshipHandler
from memory.controllers.sticker_controller import StickerController
from memory.generation.memory_model_pool import MemoryModelPool
from memory.generation.memory_output_policy import (
    MemoryDocumentPolicy,
    MemoryDocumentSchemas,
    MemoryOutputLimits,
    MemoryOutputPolicy,
)
from memory.memory_eviction_service import MemoryEvictionService
from memory.memory_pipeline import MemoryPipeline
from memory.memory_policy import MemoryPolicy
from memory.memory_state_store import MemoryStateStore
from memory.repositories.episode_memory_repository import EpisodeMemoryRepository
from memory.repositories.postgres_memory_repository import PostgresMemoryRepository
from memory.repositories.sticker_repository import StickerRepository
from memory.services.sticker_service import StickerService
from shared.configuration.global_settings_store import GlobalSettingsStore
from shared.contracts.memory import MemoryActivity
from shared.contracts.rpc.memory import (
    MemoryContextRequest,
    MemoryContextResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    PersonContextRequest,
    PersonContextResponse,
)
from shared.contracts.rpc.relationship import (
    GroupRelationshipRequest,
    GroupRelationshipResponse,
    RelationshipChatRequest,
    RelationshipListRequest,
    RelationshipListResponse,
    RelationshipSummaryRequest,
    RelationshipSummaryResponse,
)
from shared.contracts.rpc.rpc_model import SuccessResponse
from shared.contracts.rpc.sticker import (
    StickerAddRequest,
    StickerAddResponse,
    StickerBoostRequest,
    StickerSearchRequest,
    StickerSearchResponse,
)
from shared.infrastructure.base_service import BaseService
from shared.infrastructure.database import Database
from shared.infrastructure.nacos_agent_definition_store import NacosAgentDefinitionStore
from shared.infrastructure.service_config import ServiceConfig
from shared.persistence.repositories.relationship_repository import RelationshipRepository
from shared.utils.lfu import LazyLFU, LFUConfig


# 提供记忆服务能力
class MemoryService(BaseService):
    name = "memory"

    # 启动服务
    async def on_start(self) -> None:
        self._settings = await GlobalSettingsStore(self.cfg.nacos).load()
        self._memory_config = self._settings.memory
        self._grounding_config = self._settings.grounding

        # 中文分词首次加载会阻塞事件循环，必须在开始接收 NATS 请求前完成。
        await asyncio.to_thread(jieba.initialize)

        self._memory_activity_sub = None
        self._definitions = NacosAgentDefinitionStore(self.cfg.nacos)
        self._db = Database()
        await self._db.connect()
        self._memory_lfu = LazyLFU(LFUConfig(**self._settings.lfu.memory.model_dump()))
        self._sticker_svc = StickerService(
            StickerRepository(self._db),
            self._settings.sticker,
        )
        self._memory_repo = PostgresMemoryRepository(
            self._db,
            MemoryPolicy(
                dormant_threshold=self._memory_config.dormant_threshold,
                delete_threshold=self._memory_config.delete_threshold,
                strength_max=self._memory_config.strength_max,
                deletable_reference_count=self._memory_config.deletable_reference_count,
                recall_count_increment=self._memory_config.recall_count_increment,
                retrieval_weights=self._memory_config.retrieval_weights.model_dump(),
                lfu=self._memory_lfu,
            ),
            self._memory_config,
        )
        self._relationship_repo = RelationshipRepository(
            self._db,
            self._settings.relationship_storage,
        )
        self._episode_repo = EpisodeMemoryRepository(
            self._db,
            self._memory_config,
            self._memory_lfu,
        )
        self._memory_eviction = MemoryEvictionService(
            self._db,
            self._memory_lfu,
            record_capacity_per_owner=self._memory_config.record_capacity_per_owner,
            atom_capacity_per_owner=self._memory_config.atom_capacity_per_owner,
            deletable_reference_count=self._memory_config.deletable_reference_count,
        )
        self._memory_queries = MemoryQueryHandler(
            self._memory_repo,
            self._episode_repo,
            self._grounding_config,
        )
        self._relationships = RelationshipHandler(
            self._relationship_repo,
            self._definitions,
            self._settings,
        )
        self._cleanup_service = MemoryCleanupService(
            self._sticker_svc,
            self._memory_repo,
            self._memory_config.data_dir,
            self._memory_config.file_max_age_sec,
        )

        self._sticker_ctrl = StickerController(self._sticker_svc)
        await self.bus.reply_model("sticker.add.request", StickerAddRequest, StickerAddResponse, self._sticker_ctrl.add)
        await self.bus.reply_model(
            "sticker.search.request",
            StickerSearchRequest,
            StickerSearchResponse,
            self._sticker_ctrl.search,
        )
        await self.bus.reply_model(
            "sticker.boost.request", StickerBoostRequest, SuccessResponse, self._sticker_ctrl.boost
        )

        await self.bus.reply_model(
            "memory.search.request", MemorySearchRequest, MemorySearchResponse, self._memory_queries.search
        )
        await self.bus.reply_model(
            "memory.context.request", MemoryContextRequest, MemoryContextResponse, self._memory_queries.context
        )
        await self.bus.reply_model(
            "memory.person-context.request",
            PersonContextRequest,
            PersonContextResponse,
            self._memory_queries.person_context,
        )
        await self.bus.reply_model(
            "relationship.chat.request",
            RelationshipChatRequest,
            RelationshipSummaryResponse,
            self._relationships.chat,
        )
        await self.bus.reply_model(
            "relationship.summary.request",
            RelationshipSummaryRequest,
            RelationshipSummaryResponse,
            self._relationships.summary,
        )
        await self.bus.reply_model(
            "relationship.list.request",
            RelationshipListRequest,
            RelationshipListResponse,
            self._relationships.list_people,
        )
        await self.bus.reply_model(
            "relationship.group.request",
            GroupRelationshipRequest,
            GroupRelationshipResponse,
            self._relationships.group,
        )

        self.scheduler.add_job(
            self._cleanup_service.cleanup,
            "interval",
            seconds=self._memory_config.cleanup_interval_sec,
        )
        await self.bus.ensure_stream("MEMORY_ACTIVITY_EVENTS", ["memory.activity"])
        activity_kv = await self.bus.key_value("MEMORY_ACTIVITY")
        pending_kv = await self.bus.key_value("MEMORY_PENDING")
        self._memory_state = MemoryStateStore(
            activity_kv,
            pending_kv,
            quiet_window_sec=self._memory_config.extraction.quiet_window_sec,
            lease_sec=self._memory_config.worker_lease_sec,
            cas_retry_count=self._memory_config.state_cas_retry_count,
        )
        self._memory_pipeline = MemoryPipeline(
            repo=self._episode_repo,
            state=self._memory_state,
            models=MemoryModelPool(
                self._definitions,
                self._settings.llm,
                self._settings.observability,
            ),
            bus=self.bus,
            config=self._memory_config,
            output_policy=MemoryOutputPolicy(
                MemoryOutputLimits.model_validate(self._memory_config.generation.output_limits)
            ),
            document_policy=MemoryDocumentPolicy(
                MemoryDocumentSchemas.model_validate(self._memory_config.document_schemas)
            ),
            eviction=self._memory_eviction,
        )
        self._memory_activity_sub = await self.bus.subscribe_durable_model(
            "memory.activity",
            durable="memory-activity-v1",
            queue="memory-activity-v1",
            message_type=MemoryActivity,
            handler=self._memory_state.record_activity,
        )
        self.scheduler.add_job(
            self._memory_pipeline.process_due_activities,
            "interval",
            seconds=self._memory_config.extraction.scheduler_poll_sec,
        )
        self.scheduler.add_job(
            self._memory_pipeline.process_ready_consolidations,
            "interval",
            seconds=self._memory_config.consolidation.scheduler_poll_sec,
        )

    # 停止服务
    async def on_stop(self) -> None:
        if self._memory_activity_sub is not None:
            self._memory_activity_sub.unsubscribe()
        await self._db.close()


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = MemoryService(await ServiceConfig.load("memory"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
