from __future__ import annotations

import time
from dataclasses import dataclass, field
from string import Template
from typing import Callable

from shared.contracts.relationship_policy_config import RelationshipPolicyConfig
from shared.lfu import LazyLFU, LFUState


# 表示联系人关系数据
@dataclass(frozen=True)
class PersonRelationship:
    familiarity: float
    affinity: float
    trust: float
    importance: float
    lfu_state: dict[str, dict[str, int | float]] = field(default_factory=dict, compare=False, repr=False)
    ceiling_policy: str = field(default="default", compare=False, repr=False)


# 表示群聊关系数据
@dataclass(frozen=True)
class GroupRelationship:
    familiarity: float
    belonging: float
    affinity: float
    activity_willingness: float
    lfu_state: dict[str, dict[str, int | float]] = field(default_factory=dict, compare=False, repr=False)


# 表示关系上限数据
@dataclass(frozen=True)
class RelationshipCeilings:
    default: float
    whitelist: float
    person_whitelist: frozenset[str]
    group_whitelist: frozenset[str]

    # 处理联系人事件
    def person(self, person_id: str) -> float:
        return self.whitelist if person_id in self.person_whitelist else self.default

    # 处理群聊事件
    def group(self, group_id: str) -> float:
        return self.whitelist if group_id in self.group_whitelist else self.default


# 封装关系策略规则
class RelationshipPolicy:
    # 初始化当前实例
    def __init__(
        self,
        ceilings: RelationshipCeilings,
        config: RelationshipPolicyConfig,
        lfu: LazyLFU,
        now_value: Callable[[], float] = time.time,
    ) -> None:
        self._ceilings = ceilings
        self._config = config
        self._lfu = lfu
        self._now_value = now_value

    def _state(
        self,
        states: dict[str, dict[str, int | float]],
        key: str,
        now: float,
        fallback_score: float = 0.0,
    ) -> LFUState:
        return self._lfu.state_from_mapping(states.get(key), now, score=max(0.0, fallback_score))

    @staticmethod
    def _stored(states: dict[str, LFUState]) -> dict[str, dict[str, int | float]]:
        return {key: value.as_dict() for key, value in states.items()}

    def _person_states(self, current: PersonRelationship, now: float) -> dict[str, LFUState]:
        stored = current.lfu_state
        return {
            "familiarity": self._state(stored, "familiarity", now, current.familiarity),
            "affinity_positive": self._state(stored, "affinity_positive", now, max(0.0, current.affinity)),
            "affinity_negative": self._state(stored, "affinity_negative", now, max(0.0, -current.affinity)),
            "trust_positive": self._state(stored, "trust_positive", now, current.trust),
            "trust_negative": self._state(stored, "trust_negative", now),
            "importance": self._state(stored, "importance", now, current.importance),
        }

    def _group_states(self, current: GroupRelationship, now: float) -> dict[str, LFUState]:
        stored = current.lfu_state
        return {
            "familiarity": self._state(stored, "familiarity", now, current.familiarity),
            "belonging": self._state(stored, "belonging", now, current.belonging),
            "affinity_positive": self._state(stored, "affinity_positive", now, max(0.0, current.affinity)),
            "affinity_negative": self._state(stored, "affinity_negative", now, max(0.0, -current.affinity)),
            "activity_positive": self._state(
                stored,
                "activity_positive",
                now,
                current.activity_willingness,
            ),
            "activity_negative": self._state(stored, "activity_negative", now),
        }

    def project_person(
        self,
        person_id: str,
        current: PersonRelationship,
        now: float | None = None,
    ) -> PersonRelationship:
        moment = self._now_value() if now is None else now
        states = self._person_states(current, moment)
        ceiling = (
            self._ceilings.whitelist
            if current.ceiling_policy == "whitelist"
            else self._ceilings.person(person_id)
        )
        affinity = self._lfu.score(states["affinity_positive"], moment) - self._lfu.score(
            states["affinity_negative"], moment
        )
        trust = self._lfu.score(states["trust_positive"], moment) - self._lfu.score(
            states["trust_negative"], moment
        )
        return PersonRelationship(
            familiarity=min(ceiling, self._lfu.score(states["familiarity"], moment)),
            affinity=max(-ceiling, min(ceiling, affinity)),
            trust=max(self._config.bounds.score_min, min(ceiling, trust)),
            importance=min(ceiling, self._lfu.score(states["importance"], moment)),
            lfu_state=self._stored(states),
            ceiling_policy=current.ceiling_policy,
        )

    def project_group(
        self,
        group_id: str,
        current: GroupRelationship,
        now: float | None = None,
    ) -> GroupRelationship:
        moment = self._now_value() if now is None else now
        states = self._group_states(current, moment)
        ceiling = self._ceilings.group(group_id)
        affinity = self._lfu.score(states["affinity_positive"], moment) - self._lfu.score(
            states["affinity_negative"], moment
        )
        activity = self._lfu.score(states["activity_positive"], moment) - self._lfu.score(
            states["activity_negative"], moment
        )
        return GroupRelationship(
            familiarity=min(ceiling, self._lfu.score(states["familiarity"], moment)),
            belonging=min(ceiling, self._lfu.score(states["belonging"], moment)),
            affinity=max(-ceiling, min(ceiling, affinity)),
            activity_willingness=max(self._config.bounds.score_min, min(ceiling, activity)),
            lfu_state=self._stored(states),
        )

    # 处理会话
    def on_conversation(
        self,
        person_id: str,
        current: PersonRelationship,
        quality: float,
    ) -> PersonRelationship:
        now = self._now_value()
        quality = max(self._config.bounds.quality_min, min(self._config.bounds.quality_max, quality))
        states = self._person_states(current, now)
        states["familiarity"] = self._lfu.access(states["familiarity"], now)
        if quality > self._config.bounds.neutral_quality:
            states["affinity_positive"] = self._lfu.access(states["affinity_positive"], now)
        elif quality < self._config.bounds.neutral_quality:
            states["affinity_negative"] = self._lfu.access(states["affinity_negative"], now)
        return self.project_person(
            person_id,
            PersonRelationship(
                0.0,
                0.0,
                0.0,
                0.0,
                self._stored(states),
                current.ceiling_policy,
            ),
            now,
        )

    # 处理礼物
    def on_gift(
        self,
        person_id: str,
        current: PersonRelationship,
        amount: float,
    ) -> PersonRelationship:

        now = self._now_value()
        config = self._config.gift
        normalized_amount = max(self._config.bounds.gift_amount_min, amount)
        familiarity_hits = max(1, min(8, round(normalized_amount / config.familiarity_amount_divisor)))
        importance_hits = max(1, min(8, round(normalized_amount / config.importance_amount_divisor)))
        states = self._person_states(current, now)
        states["familiarity"] = self._lfu.access(states["familiarity"], now, familiarity_hits)
        states["importance"] = self._lfu.access(states["importance"], now, importance_hits)
        return self.project_person(
            person_id,
            PersonRelationship(
                0.0,
                0.0,
                0.0,
                0.0,
                self._stored(states),
                current.ceiling_policy,
            ),
            now,
        )

    # 处理信任事件
    def on_trust_event(
        self,
        person_id: str,
        current: PersonRelationship,
        positive: bool,
    ) -> PersonRelationship:
        now = self._now_value()
        states = self._person_states(current, now)
        key = "trust_positive" if positive else "trust_negative"
        states[key] = self._lfu.access(states[key], now)
        return self.project_person(
            person_id,
            PersonRelationship(
                0.0,
                0.0,
                0.0,
                0.0,
                self._stored(states),
                current.ceiling_policy,
            ),
            now,
        )

    # 处理群聊会话
    def on_group_conversation(
        self,
        group_id: str,
        current: GroupRelationship,
        quality: float,
    ) -> GroupRelationship:
        now = self._now_value()
        quality = max(self._config.bounds.quality_min, min(self._config.bounds.quality_max, quality))
        states = self._group_states(current, now)
        states["familiarity"] = self._lfu.access(states["familiarity"], now)
        if quality > self._config.bounds.neutral_quality:
            for key in ("belonging", "affinity_positive", "activity_positive"):
                states[key] = self._lfu.access(states[key], now)
        elif quality < self._config.bounds.neutral_quality:
            for key in ("affinity_negative", "activity_negative"):
                states[key] = self._lfu.access(states[key], now)
        return self.project_group(
            group_id,
            GroupRelationship(0.0, 0.0, 0.0, 0.0, self._stored(states)),
            now,
        )

    # 生成联系人摘要
    def summarize_person(self, relationship: PersonRelationship) -> str:
        config = self._config.summary
        familiarity = (
            config.familiarity_high_text
            if relationship.familiarity >= config.familiarity_high_threshold
            else config.familiarity_medium_text
            if relationship.familiarity >= config.familiarity_medium_threshold
            else config.familiarity_low_text
        )
        affinity = (
            config.affinity_high_text
            if relationship.affinity >= config.affinity_high_threshold
            else config.affinity_positive_text
            if relationship.affinity >= config.affinity_positive_threshold
            else config.affinity_negative_text
            if relationship.affinity < config.affinity_negative_threshold
            else config.affinity_neutral_text
        )
        trust = (
            config.trust_high_text
            if relationship.trust >= config.trust_high_threshold
            else config.trust_medium_text
            if relationship.trust >= config.trust_medium_threshold
            else config.trust_low_text
        )
        return Template(config.template).substitute(
            familiarity=familiarity,
            affinity=affinity,
            trust=trust,
        )
