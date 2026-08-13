
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ai.llm.tier import ModelCapability, Tier


# 表示模型候选项数据
@dataclass
class ModelCandidate:

    id: str
    provider: str
    tier: Tier
    capabilities: list[ModelCapability] = field(default_factory=lambda: [ModelCapability.CHAT])
    supports_thinking: bool = False


# 表示模型目标数据
@dataclass
class ModelTarget:

    candidate: ModelCandidate
    timeout_ms: int


# 记录模型调用健康状态
class ModelHealthStore:

    # 初始化当前实例
    def __init__(self, fail_threshold: int, recover_after_sec: int) -> None:
        self._fail_threshold = fail_threshold
        self._recover_after_sec = recover_after_sec
        self._fails: dict[str, int] = {}
        self._last_fail_at: dict[str, float] = {}

    # 判断是否允许工具调用
    def allow_call(self, model_id: str) -> bool:
        fails = self._fails.get(model_id, 0)
        if fails < self._fail_threshold:
            return True
        last_fail = self._last_fail_at.get(model_id, 0)
        return time.time() - last_fail > self._recover_after_sec

    # 标记失败状态
    def mark_failure(self, model_id: str) -> None:
        self._fails[model_id] = self._fails.get(model_id, 0) + 1
        self._last_fail_at[model_id] = time.time()

    # 标记成功状态
    def mark_success(self, model_id: str) -> None:
        self._fails.pop(model_id, None)


# 选择满足要求的可用模型
class ModelSelector:

    # 初始化当前实例
    def __init__(self, model_cfg: dict, timeout_ms: int, health_store: ModelHealthStore) -> None:
        self._cfg = model_cfg
        self._timeout_ms = int(timeout_ms)
        self._health = health_store

    # 筛选指定档位的模型
    def _models_in_tier(self, tier: Tier) -> list[ModelCandidate]:
        tier_key = tier.value
        models = []
        for m in self._cfg[tier_key]:
            models.append(
                ModelCandidate(
                    id=m["id"],
                    provider=m["provider"],
                    tier=tier,
                    supports_thinking=m["thinking"],
                )
            )
        return models

    # 选择候选项
    def select_candidates(self, capability: ModelCapability, tier: Tier | None = None, preferred: str = "") -> list[ModelTarget]:
        tier = tier or Tier.STANDARD
        candidates = self._models_in_tier(tier)
        if preferred:
            candidates.sort(key=lambda c: 0 if c.id == preferred else 1)

        targets = []
        for c in candidates:
            if self._health.allow_call(c.id):
                targets.append(ModelTarget(candidate=c, timeout_ms=self._timeout_ms))
        return targets

    # 选择聊天候选项
    def select_chat_candidates(self, thinking: bool = False, tier: Tier | None = None, preferred: str = "") -> list[ModelTarget]:
        targets = self.select_candidates(ModelCapability.CHAT, tier, preferred)
        if thinking:
            targets = [t for t in targets if t.candidate.supports_thinking]
        return targets
