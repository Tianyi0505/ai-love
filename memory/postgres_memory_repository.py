from __future__ import annotations

from datetime import datetime, timezone

import bm25s
import jieba
from sqlalchemy import delete, or_, select, update

from memory.memory_policy import (
    MemoryAccessContext,
    MemoryPolicy,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)
from shared import database_models as m
from shared.global_settings import MemorySettings


# 使用PostgreSQL持久化记忆
class PostgresMemoryRepository:
    # 初始化当前实例
    def __init__(self, db, policy: MemoryPolicy, config: MemorySettings) -> None:
        self._db = db
        self._policy = policy
        self._config = config

    # 检索匹配内容
    async def search(
        self,
        ai_id: str,
        query: str,
        top_k: int,
        person_id: str | None,
        session_id: str | None,
        active_session_actors: list[str],
    ) -> list[dict]:
        person_filter = int(person_id) if person_id else None
        conditions = [
            m.Memory.dormant.is_(False),
            or_(
                m.Memory.owner_ai_id == ai_id,
                m.Memory.shared_with.any(ai_id),
                m.Memory.scope == "session",
            ),
        ]
        if person_filter:
            conditions.append(
                or_(
                    m.Memory.person_id.is_(None),
                    m.Memory.person_id == person_filter,
                )
            )
        async with self._db.session() as session:
            result = await session.execute(
                select(m.Memory)
                .where(*conditions)
                .order_by(
                    m.Memory.last_recalled_at.desc().nulls_last(),
                    m.Memory.created_at.desc(),
                )
                .limit(self._config.database_candidate_limit)
            )
            memories = list(result.scalars())
        context = MemoryAccessContext(ai_id, session_id, frozenset(active_session_actors))
        readable = []
        for row in memories:
            memory = self._record(row)
            if not self._policy.can_read(memory, context):
                continue
            readable.append((memory, row.person_id))
        relevance_by_id = self._relevance(readable, query)
        ranked = [
            (
                self._policy.retrieval_score(
                    memory,
                    relevance_by_id[memory.memory_id],
                ),
                memory,
                memory_person_id,
            )
            for memory, memory_person_id in readable
            if memory.memory_id in relevance_by_id
        ]
        ranked.sort(key=lambda item: item[0], reverse=True)

        results = []
        selected = ranked[:top_k]
        async with self._db.session() as session:
            async with session.begin():
                for score, memory, memory_person_id in selected:
                    locked_row = (
                        await session.execute(
                            select(m.Memory)
                            .where(m.Memory.memory_id == int(memory.memory_id))
                            .with_for_update()
                        )
                    ).scalar_one()
                    recalled = self._policy.recall(self._record(locked_row))
                    await session.execute(
                        update(m.Memory)
                        .where(m.Memory.memory_id == int(memory.memory_id))
                        .values(
                            strength=recalled.strength,
                            last_strength_at=datetime.fromtimestamp(
                                recalled.last_strength_at,
                                tz=timezone.utc,
                            ),
                            last_recalled_at=datetime.fromtimestamp(
                                recalled.last_strength_at,
                                tz=timezone.utc,
                            ),
                            recall_count=recalled.recall_count,
                            lfu_state=recalled.lfu_state,
                        )
                    )
                    results.append(
                        {
                            "memory_id": memory.memory_id,
                            "person_id": str(memory_person_id) if memory_person_id else "",
                            "content": memory.content,
                            "memory_type": memory.memory_type.value,
                            "scope": memory.scope.value,
                            "confidence": memory.confidence,
                            "retrieval_score": score,
                        }
                    )
        return results

    # 清理过期数据
    async def cleanup(self) -> dict[str, int]:
        async with self._db.session() as session:
            result = await session.execute(select(m.Memory))
            dormant_ids = []
            delete_ids = []
            for row in result.scalars():
                memory = self._record(row)
                if self._policy.can_delete(memory):
                    delete_ids.append(int(memory.memory_id))
                elif self._policy.is_dormant(memory):
                    dormant_ids.append(int(memory.memory_id))
        if dormant_ids:
            async with self._db.session() as session:
                await session.execute(update(m.Memory).where(m.Memory.memory_id.in_(dormant_ids)).values(dormant=True))
                await session.commit()
        if delete_ids:
            async with self._db.session() as session:
                await session.execute(delete(m.Memory).where(m.Memory.memory_id.in_(delete_ids)))
                await session.commit()
        return {"dormant": len(dormant_ids), "deleted": len(delete_ids)}

    # 记录模型调用结果
    @staticmethod
    def _record(row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=str(row.memory_id),
            owner_ai_id=row.owner_ai_id,
            scope=MemoryScope(row.scope),
            memory_type=MemoryType(row.memory_type),
            content=row.content,
            importance=float(row.importance),
            strength=float(row.strength),
            confidence=float(row.confidence),
            emotion_intensity=float(row.emotion_intensity),
            session_id=row.session_id,
            shared_with=frozenset(row.shared_with),
            protected=bool(row.protected),
            consolidated=bool(row.consolidated),
            reference_count=int(row.reference_count),
            last_strength_at=float(row.last_strength_at.timestamp()),
            last_recalled_at=float(row.last_recalled_at.timestamp()) if row.last_recalled_at else None,
            recall_count=int(row.recall_count),
            lfu_state=dict(row.lfu_state or {}),
        )

    # 计算记忆相关度
    def _relevance(
        self,
        memories: list[tuple[MemoryRecord, int | None]],
        query: str,
    ) -> dict[str, float]:
        if not query:
            return {memory.memory_id: self._config.empty_query_relevance for memory, _ in memories}
        if not memories:
            return {}
        retriever = bm25s.BM25()
        retriever.index(
            [jieba.lcut(memory.content) for memory, _ in memories],
            show_progress=False,
        )
        candidates, scores = retriever.retrieve(
            [jieba.lcut(query)],
            corpus=[memory for memory, _ in memories],
            k=len(memories),
            show_progress=False,
        )
        maximum = float(scores[0].max())
        if maximum == 0:
            return {}
        return {
            memory.memory_id: float(score) / maximum
            for memory, score in zip(candidates[0], scores[0], strict=True)
            if score > 0
        }
