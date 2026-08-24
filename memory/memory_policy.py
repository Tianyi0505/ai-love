from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum

from shared.utils.lfu import LazyLFU, LFUState


# 定义记忆作用域枚举
class MemoryScope(str, Enum):
    PRIVATE = "private"
    SESSION = "session"
    SHARED = "shared"


# 定义记忆类型枚举
class MemoryType(str, Enum):
    OBSERVATION = "observation"
    FACT = "fact"
    BELIEF = "belief"
    FEELING = "feeling"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    COMMITMENT = "commitment"


PROTECTED_TYPES = frozenset({MemoryType.COMMITMENT})


# 表示记忆记录数据
@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    owner_ai_id: str | None
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    importance: float
    strength: float
    confidence: float
    emotion_intensity: float
    session_id: str | None
    shared_with: frozenset[str]
    protected: bool
    consolidated: bool
    reference_count: int
    last_strength_at: float
    last_recalled_at: float | None
    recall_count: int
    lfu_state: dict[str, int | float] = field(default_factory=dict)


# 描述记忆访问上下文
@dataclass(frozen=True)
class MemoryAccessContext:
    requester_ai_id: str
    session_id: str | None
    active_session_actors: frozenset[str]


# 封装记忆策略规则
class MemoryPolicy:
    # 初始化当前实例
    def __init__(
        self,
        dormant_threshold: float,
        delete_threshold: float,
        strength_max: float,
        deletable_reference_count: int,
        recall_count_increment: int,
        retrieval_weights: dict,
        lfu: LazyLFU,
    ) -> None:
        self._dormant_threshold = dormant_threshold
        self._delete_threshold = delete_threshold
        self._strength_max = strength_max
        self._deletable_reference_count = deletable_reference_count
        self._recall_count_increment = recall_count_increment
        self._retrieval_weights = retrieval_weights
        self._lfu = lfu

    def _state(self, memory: MemoryRecord) -> LFUState:
        if memory.lfu_state:
            return LFUState.from_mapping(memory.lfu_state)
        return LFUState(
            counter=self._lfu.counter_for_score(memory.strength),
            last_decay_at=memory.last_strength_at,
        )

    # 计算当前记忆强度
    def current_strength(self, memory: MemoryRecord, now: float | None = None) -> float:
        moment = time.time() if now is None else now
        return self._lfu.score(self._state(memory), moment)

    # 判断是否可以读取
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

    # 判断是否休眠状态
    def is_dormant(self, memory: MemoryRecord, now: float | None = None) -> bool:
        return self.current_strength(memory, now) < self._dormant_threshold

    # 判断是否可以删除
    def can_delete(self, memory: MemoryRecord, now: float | None = None) -> bool:
        if memory.protected or memory.memory_type in PROTECTED_TYPES:
            return False
        return (
            memory.consolidated
            and memory.reference_count == self._deletable_reference_count
            and self.current_strength(memory, now) < self._delete_threshold
        )

    # 召回相关记忆
    def recall(self, memory: MemoryRecord, now: float | None = None) -> MemoryRecord:
        moment = time.time() if now is None else now
        state = self._lfu.access(self._state(memory), moment)
        strength = min(self._strength_max, self._lfu.score(state, moment))
        return replace(
            memory,
            strength=strength,
            last_strength_at=moment,
            last_recalled_at=moment,
            recall_count=memory.recall_count + self._recall_count_increment,
            lfu_state=state.as_dict(),
        )

    # 计算记忆检索分数
    def retrieval_score(self, memory: MemoryRecord, relevance: float, now: float | None = None) -> float:

        strength = self.current_strength(memory, now)
        return (
            relevance * float(self._retrieval_weights["relevance"])
            + strength * float(self._retrieval_weights["strength"])
            + memory.importance * float(self._retrieval_weights["importance"])
            + memory.confidence * float(self._retrieval_weights["confidence"])
            + memory.emotion_intensity * float(self._retrieval_weights["emotion_intensity"])
        )
