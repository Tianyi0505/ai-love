from __future__ import annotations

import asyncio

import jieba

from memory.episode_memory_repository import EpisodeMemoryRepository
from memory.memory_cleanup_service import MemoryCleanupService
from memory.memory_eviction_service import MemoryEvictionService
from memory.memory_model_pool import MemoryModelPool
from memory.memory_output_policy import (
    MemoryDocumentPolicy,
    MemoryDocumentSchemas,
    MemoryOutputLimits,
    MemoryOutputPolicy,
)
from memory.memory_pipeline import MemoryPipeline
from memory.memory_policy import MemoryPolicy
from memory.memory_query_handler import MemoryQueryHandler
from memory.memory_state_store import MemoryStateStore
from memory.postgres_memory_repository import PostgresMemoryRepository
from memory.relationship_handler import RelationshipHandler
from memory.sticker_controller import StickerController
from memory.sticker_repository import StickerRepository
from memory.sticker_service import StickerService
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
from shared.global_settings_store import GlobalSettingsStore
from shared.lfu import LazyLFU, LFUConfig
from shared.relationship_repository import RelationshipRepository


# 提供进程内记忆模块能力
class MemoryModule:
    def __init__(self, *, config_provider, bus, scheduler, database, definitions, model_factory=None) -> None:
        self._config_provider = config_provider
        self._bus = bus
        self._scheduler = scheduler
        self._db = database
        self._definitions = definitions
        self._subscriptions = []
        self._model_factory = model_factory

    # 启动模块
    async def start(self) -> None:
        self._settings = await GlobalSettingsStore(self._config_provider).load()
        self._memory_config = self._settings.memory
        self._grounding_config = self._settings.grounding

        # 中文分词首次加载会阻塞事件循环，必须在开始接收 NATS 请求前完成。
        await asyncio.to_thread(jieba.initialize)

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
        self._subscriptions.extend(
            [
                await self._bus.reply_model(
                    "sticker.add.request", StickerAddRequest, StickerAddResponse, self._sticker_ctrl.add
                ),
                await self._bus.reply_model(
                    "sticker.search.request",
                    StickerSearchRequest,
                    StickerSearchResponse,
                    self._sticker_ctrl.search,
                ),
                await self._bus.reply_model(
                    "sticker.boost.request", StickerBoostRequest, SuccessResponse, self._sticker_ctrl.boost
                ),
                await self._bus.reply_model(
                    "memory.search.request", MemorySearchRequest, MemorySearchResponse, self._memory_queries.search
                ),
                await self._bus.reply_model(
                    "memory.context.request", MemoryContextRequest, MemoryContextResponse, self._memory_queries.context
                ),
                await self._bus.reply_model(
                    "memory.person-context.request",
                    PersonContextRequest,
                    PersonContextResponse,
                    self._memory_queries.person_context,
                ),
                await self._bus.reply_model(
                    "relationship.chat.request",
                    RelationshipChatRequest,
                    RelationshipSummaryResponse,
                    self._relationships.chat,
                ),
                await self._bus.reply_model(
                    "relationship.summary.request",
                    RelationshipSummaryRequest,
                    RelationshipSummaryResponse,
                    self._relationships.summary,
                ),
                await self._bus.reply_model(
                    "relationship.list.request",
                    RelationshipListRequest,
                    RelationshipListResponse,
                    self._relationships.list_people,
                ),
                await self._bus.reply_model(
                    "relationship.group.request",
                    GroupRelationshipRequest,
                    GroupRelationshipResponse,
                    self._relationships.group,
                ),
            ]
        )

        self._scheduler.add_job(
            self._cleanup_service.cleanup,
            "interval",
            seconds=self._memory_config.cleanup_interval_sec,
        )
        await self._bus.ensure_stream("MEMORY_ACTIVITY_EVENTS", ["memory.activity"])
        activity_kv = await self._bus.key_value("MEMORY_ACTIVITY")
        pending_kv = await self._bus.key_value("MEMORY_PENDING")
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
                model_factory=self._model_factory,
            ),
            bus=self._bus,
            config=self._memory_config,
            output_policy=MemoryOutputPolicy(
                MemoryOutputLimits.model_validate(self._memory_config.generation.output_limits)
            ),
            document_policy=MemoryDocumentPolicy(
                MemoryDocumentSchemas.model_validate(self._memory_config.document_schemas)
            ),
            eviction=self._memory_eviction,
        )
        self._subscriptions.append(
            await self._bus.subscribe_durable_model(
                "memory.activity",
                durable="memory-activity-v1",
                queue="memory-activity-v1",
                message_type=MemoryActivity,
                handler=self._memory_state.record_activity,
            )
        )
        self._scheduler.add_job(
            self._memory_pipeline.process_due_activities,
            "interval",
            seconds=self._memory_config.extraction.scheduler_poll_sec,
        )
        self._scheduler.add_job(
            self._memory_pipeline.process_ready_consolidations,
            "interval",
            seconds=self._memory_config.consolidation.scheduler_poll_sec,
        )

    # 停止模块
    async def stop(self) -> None:
        for subscription in reversed(self._subscriptions):
            subscription.unsubscribe()
        self._subscriptions.clear()
