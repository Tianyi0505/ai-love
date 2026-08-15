
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, or_, select, update

from memory.memory_policy import (
    MemoryAccessContext,
    MemoryPolicy,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)
from shared.infrastructure import models as m
from shared.infrastructure.snowflake import new_snowflake_id


# 使用PostgreSQL持久化记忆
class PostgresMemoryRepo:
    # 初始化当前实例
    def __init__(self, db, policy: MemoryPolicy, config: dict) -> None:
        self._db = db
        self._policy = policy
        self._config = config

    # 写入数据
    async def write(self, ai_id: str, entries: list[dict]) -> None:
        for entry in entries:
            scope = MemoryScope(entry["scope"])
            memory_type = MemoryType(entry["memory_type"])
            async with self._db.session() as session:
                session.add(
                    m.Memory(
                        memory_id=int(new_snowflake_id()),
                        owner_ai_id=ai_id,
                        person_id=int(entry["person_id"]) if entry.get("person_id") else None,
                        session_id=entry.get("session_id") or None,
                        scope=scope.value,
                        memory_type=memory_type.value,
                        content=str(entry.get("content", "")),
                        importance=self._unit(entry["importance"]),
                        strength=self._unit(entry["strength"]),
                        confidence=self._unit(entry["confidence"]),
                        emotion_intensity=self._unit(entry["emotion_intensity"]),
                        protected=bool(
                            entry.get("protected", memory_type == MemoryType.COMMITMENT)
                        ),
                        source=entry.get("source", {}),
                        shared_with=list(entry.get("shared_with", [])),
                        consolidated=bool(entry["consolidated"]),
                        reference_count=int(entry.get("reference_count", 0)),
                        created_at=datetime.now(timezone.utc),
                        last_strength_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

    # 检索匹配内容
    async def search(
        self,
        ai_id: str,
        query: str,
        top_k: int,
        person_id: str = "",
        session_id: str = "",
        active_session_actors: list[str] | None = None,
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
                .limit(int(self._config["database_candidate_limit"]))
            )
            memories = list(result.scalars())
        context = MemoryAccessContext(ai_id, session_id, frozenset(active_session_actors or []))
        ranked = []
        for row in memories:
            memory = self._record(row)
            if not self._policy.can_read(memory, context):
                continue
            relevance = self._relevance(memory.content, query)
            if query and relevance <= 0:
                continue
            ranked.append((self._policy.retrieval_score(memory, relevance), memory, row.person_id))
        ranked.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, memory, memory_person_id in ranked[:top_k]:
            recalled = self._policy.recall(memory)
            async with self._db.session() as session:
                await session.execute(
                    update(m.Memory)
                    .where(m.Memory.memory_id == int(memory.memory_id))
                    .values(
                        strength=recalled.strength,
                        last_strength_at=datetime.fromtimestamp(
                            recalled.last_strength_at, tz=timezone.utc
                        ),
                        last_recalled_at=datetime.fromtimestamp(
                            recalled.last_strength_at, tz=timezone.utc
                        ),
                        recall_count=recalled.recall_count,
                    )
                )
                await session.commit()
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
                await session.execute(
                    update(m.Memory)
                    .where(m.Memory.memory_id.in_(dormant_ids))
                    .values(dormant=True)
                )
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
            owner_ai_id=row.owner_ai_id or "",
            scope=MemoryScope(row.scope),
            memory_type=MemoryType(row.memory_type),
            content=row.content,
            importance=float(row.importance),
            strength=float(row.strength),
            confidence=float(row.confidence),
            emotion_intensity=float(row.emotion_intensity),
            session_id=row.session_id or "",
            shared_with=frozenset(row.shared_with or []),
            protected=bool(row.protected),
            consolidated=bool(row.consolidated),
            reference_count=int(row.reference_count),
            last_strength_at=float(row.last_strength_at.timestamp()) if row.last_strength_at else 0.0,
            last_recalled_at=float(row.last_recalled_at.timestamp()) if row.last_recalled_at else 0.0,
            recall_count=int(row.recall_count),
        )

    # 计算记忆相关度
    def _relevance(self, content: str, query: str) -> float:
        if not query:
            return float(self._config["empty_query_relevance"])
        content_chars = set(content.lower())
        query_chars = set(query.lower())
        if not query_chars:
            return 0.0
        return len(content_chars & query_chars) / len(query_chars)

    # 将数值限制在单位区间
    @staticmethod
    def _unit(value) -> float:
        number = float(value)
        if number > 1:
            number /= 100.0
        return max(0.0, min(1.0, number))
