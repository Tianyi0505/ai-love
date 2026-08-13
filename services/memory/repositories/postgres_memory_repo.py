
from __future__ import annotations

import uuid

from services.memory.memory_policy import (
    MemoryAccessContext,
    MemoryPolicy,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)


class PostgresMemoryRepo:
    def __init__(self, db, policy: MemoryPolicy, config: dict) -> None:
        self._db = db
        self._policy = policy
        self._config = config

    async def write(self, ai_id: str, entries: list[dict]) -> None:
        for entry in entries:
            scope = MemoryScope(entry["scope"])
            memory_type = MemoryType(entry["memory_type"])
            await self._db.execute(
                "INSERT INTO memories("
                "memory_id, owner_ai_id, person_id, session_id, scope, memory_type, content, "
                "importance, strength, confidence, emotion_intensity, protected, source, "
                "shared_with, consolidated, reference_count"
                ") VALUES($1::uuid,$2,$3::uuid,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14,$15,$16)",
                str(uuid.uuid4()),
                ai_id,
                entry.get("person_id") or None,
                entry.get("session_id") or None,
                scope.value,
                memory_type.value,
                str(entry.get("content", "")),
                self._unit(entry["importance"]),
                self._unit(entry["strength"]),
                self._unit(entry["confidence"]),
                self._unit(entry["emotion_intensity"]),
                bool(entry.get("protected", memory_type == MemoryType.COMMITMENT)),
                __import__("json").dumps(entry.get("source", {}), ensure_ascii=False),
                list(entry.get("shared_with", [])),
                bool(entry["consolidated"]),
                int(entry.get("reference_count", 0)),
            )

    async def search(
        self,
        ai_id: str,
        query: str,
        top_k: int,
        person_id: str = "",
        session_id: str = "",
        active_session_actors: list[str] | None = None,
    ) -> list[dict]:
        rows = await self._db.fetch(
            "SELECT memory_id::text, owner_ai_id, person_id::text, session_id::text, scope, "
            "memory_type, content, importance, strength, confidence, emotion_intensity, protected, "
            "shared_with, consolidated, reference_count, extract(epoch from last_strength_at) AS last_strength_at, "
            "extract(epoch from last_recalled_at) AS last_recalled_at, recall_count "
            "FROM memories WHERE dormant=false AND (owner_ai_id=$1 OR $1=ANY(shared_with) OR scope='session') "
            "AND ($2::uuid IS NULL OR person_id IS NULL OR person_id=$2::uuid) "
            "ORDER BY last_recalled_at DESC NULLS LAST, created_at DESC LIMIT $3",
            ai_id,
            person_id or None,
            int(self._config["database_candidate_limit"]),
        )
        context = MemoryAccessContext(ai_id, session_id, frozenset(active_session_actors or []))
        ranked = []
        for row in rows:
            memory = self._record(row)
            if not self._policy.can_read(memory, context):
                continue
            relevance = self._relevance(memory.content, query)
            if query and relevance <= 0:
                continue
            ranked.append((self._policy.retrieval_score(memory, relevance), memory, row["person_id"]))
        ranked.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, memory, memory_person_id in ranked[:top_k]:
            recalled = self._policy.recall(memory)
            await self._db.execute(
                "UPDATE memories SET strength=$2, last_strength_at=to_timestamp($3), "
                "last_recalled_at=to_timestamp($3), recall_count=$4 WHERE memory_id=$1::uuid",
                memory.memory_id,
                recalled.strength,
                recalled.last_recalled_at,
                recalled.recall_count,
            )
            results.append(
                {
                    "memory_id": memory.memory_id,
                    "person_id": memory_person_id,
                    "content": memory.content,
                    "memory_type": memory.memory_type.value,
                    "scope": memory.scope.value,
                    "confidence": memory.confidence,
                    "retrieval_score": score,
                }
            )
        return results

    async def cleanup(self) -> dict[str, int]:
        rows = await self._db.fetch(
            "SELECT memory_id::text, owner_ai_id, person_id::text, session_id::text, scope, "
            "memory_type, content, importance, strength, confidence, emotion_intensity, protected, "
            "shared_with, consolidated, reference_count, extract(epoch from last_strength_at) AS last_strength_at, "
            "extract(epoch from last_recalled_at) AS last_recalled_at, recall_count FROM memories"
        )
        dormant_ids = []
        delete_ids = []
        for row in rows:
            memory = self._record(row)
            if self._policy.can_delete(memory):
                delete_ids.append(memory.memory_id)
            elif self._policy.is_dormant(memory):
                dormant_ids.append(memory.memory_id)
        if dormant_ids:
            await self._db.execute(
                "UPDATE memories SET dormant=true WHERE memory_id=ANY($1::uuid[])",
                [uuid.UUID(item) for item in dormant_ids],
            )
        if delete_ids:
            await self._db.execute(
                "DELETE FROM memories WHERE memory_id=ANY($1::uuid[])",
                [uuid.UUID(item) for item in delete_ids],
            )
        return {"dormant": len(dormant_ids), "deleted": len(delete_ids)}

    @staticmethod
    def _record(row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            owner_ai_id=row["owner_ai_id"] or "",
            scope=MemoryScope(row["scope"]),
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            importance=float(row["importance"]),
            strength=float(row["strength"]),
            confidence=float(row["confidence"]),
            emotion_intensity=float(row["emotion_intensity"]),
            session_id=row["session_id"] or "",
            shared_with=frozenset(row["shared_with"] or []),
            protected=bool(row["protected"]),
            consolidated=bool(row["consolidated"]),
            reference_count=int(row["reference_count"]),
            last_strength_at=float(row["last_strength_at"] or 0),
            last_recalled_at=float(row["last_recalled_at"] or 0),
            recall_count=int(row["recall_count"]),
        )

    def _relevance(self, content: str, query: str) -> float:
        if not query:
            return float(self._config["empty_query_relevance"])
        content_chars = set(content.lower())
        query_chars = set(query.lower())
        if not query_chars:
            return 0.0
        return len(content_chars & query_chars) / len(query_chars)

    @staticmethod
    def _unit(value) -> float:
        number = float(value)
        if number > 1:
            number /= 100.0
        return max(0.0, min(1.0, number))
