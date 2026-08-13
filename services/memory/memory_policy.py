
from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from enum import Enum


class MemoryScope(str, Enum):
    PRIVATE = "private"
    SESSION = "session"
    SHARED = "shared"


class MemoryType(str, Enum):
    OBSERVATION = "observation"
    FACT = "fact"
    BELIEF = "belief"
    FEELING = "feeling"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    COMMITMENT = "commitment"


PROTECTED_TYPES = frozenset({MemoryType.COMMITMENT})


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    owner_ai_id: str
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    importance: float
    strength: float
    confidence: float
    emotion_intensity: float = 0.0
    session_id: str = ""
    shared_with: frozenset[str] = frozenset()
    protected: bool = False
    consolidated: bool = False
    reference_count: int = 0
    last_strength_at: float = 0.0
    last_recalled_at: float = 0.0
    recall_count: int = 0


@dataclass(frozen=True)
class MemoryAccessContext:
    requester_ai_id: str
    session_id: str = ""
    active_session_actors: frozenset[str] = frozenset()


class MemoryPolicy:
    def __init__(
        self,
        half_life_sec: float = 30 * 86400,
        dormant_threshold: float = 0.2,
        delete_threshold: float = 0.05,
        recall_boost: float = 0.12,
    ) -> None:
        self._half_life = half_life_sec
        self._dormant_threshold = dormant_threshold
        self._delete_threshold = delete_threshold
        self._recall_boost = recall_boost

    def current_strength(self, memory: MemoryRecord, now: float | None = None) -> float:
        if memory.protected or memory.memory_type in PROTECTED_TYPES:
            return memory.strength
        anchor = memory.last_strength_at or memory.last_recalled_at or now or time.time()
        elapsed = max(0.0, (now or time.time()) - anchor)
        return memory.strength * math.pow(0.5, elapsed / self._half_life)

    def can_read(self, memory: MemoryRecord, context: MemoryAccessContext) -> bool:
        if memory.scope == MemoryScope.PRIVATE:
            return memory.owner_ai_id == context.requester_ai_id
        if memory.scope == MemoryScope.SHARED:
            return context.requester_ai_id == memory.owner_ai_id or context.requester_ai_id in memory.shared_with
        return (
            bool(memory.session_id)
            and memory.session_id == context.session_id
            and context.requester_ai_id in context.active_session_actors
        )
    def is_dormant(self, memory: MemoryRecord, now: float | None = None) -> bool:
        return self.current_strength(memory, now) < self._dormant_threshold

    def can_delete(self, memory: MemoryRecord, now: float | None = None) -> bool:
        if memory.protected or memory.memory_type in PROTECTED_TYPES:
            return False
        return (
            memory.consolidated
            and memory.reference_count == 0
            and self.current_strength(memory, now) < self._delete_threshold
        )

    def recall(self, memory: MemoryRecord, now: float | None = None) -> MemoryRecord:
        moment = now or time.time()
        strength = min(1.0, self.current_strength(memory, moment) + self._recall_boost)
        return replace(
            memory,
            strength=strength,
            last_strength_at=moment,
            last_recalled_at=moment,
            recall_count=memory.recall_count + 1,
        )

    def retrieval_score(self, memory: MemoryRecord, relevance: float, now: float | None = None) -> float:

        relevance = max(0.0, min(1.0, relevance))
        strength = self.current_strength(memory, now)
        return (
            relevance * 0.45
            + strength * 0.25
            + max(0.0, min(1.0, memory.importance)) * 0.15
            + max(0.0, min(1.0, memory.confidence)) * 0.1
            + max(0.0, min(1.0, memory.emotion_intensity)) * 0.05
        )
