
from __future__ import annotations

from dataclasses import dataclass, replace
from string import Template


# 表示联系人关系数据
@dataclass(frozen=True)
class PersonRelationship:
    familiarity: float = 0.0
    affinity: float = 0.0
    trust: float = 0.0
    importance: float = 0.0


# 表示群聊关系数据
@dataclass(frozen=True)
class GroupRelationship:
    familiarity: float = 0.0
    belonging: float = 0.0
    affinity: float = 0.0
    activity_willingness: float = 0.0


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
    def __init__(self, ceilings: RelationshipCeilings, config: dict) -> None:
        self._ceilings = ceilings
        self._config = config

    # 处理会话
    def on_conversation(
        self,
        person_id: str,
        current: PersonRelationship,
        quality: float,
    ) -> PersonRelationship:
        ceiling = self._ceilings.person(person_id)
        quality = max(-1.0, min(1.0, quality))
        config = self._config["conversation"]
        return replace(
            current,
            familiarity=min(ceiling, current.familiarity + float(config["familiarity_delta"])),
            affinity=max(-ceiling, min(ceiling, current.affinity + quality * float(config["affinity_quality_multiplier"]))),
        )

    # 处理礼物
    def on_gift(
        self,
        person_id: str,
        current: PersonRelationship,
        amount: float,
    ) -> PersonRelationship:

        ceiling = self._ceilings.person(person_id)
        config = self._config["gift"]
        familiarity_delta = min(
            float(config["familiarity_max_delta"]),
            max(0.0, amount) / float(config["familiarity_amount_divisor"]),
        )
        importance_delta = min(
            float(config["importance_max_delta"]),
            max(0.0, amount) / float(config["importance_amount_divisor"]),
        )
        return replace(
            current,
            familiarity=min(ceiling, current.familiarity + familiarity_delta),
            importance=min(ceiling, current.importance + importance_delta),
        )

    # 处理信任事件
    def on_trust_event(
        self,
        person_id: str,
        current: PersonRelationship,
        positive: bool,
    ) -> PersonRelationship:
        ceiling = self._ceilings.person(person_id)
        config = self._config["trust"]
        delta = float(config["positive_delta"] if positive else config["negative_delta"])
        return replace(current, trust=max(0.0, min(ceiling, current.trust + delta)))

    # 处理群聊会话
    def on_group_conversation(
        self,
        group_id: str,
        current: GroupRelationship,
        quality: float,
    ) -> GroupRelationship:
        ceiling = self._ceilings.group(group_id)
        quality = max(-1.0, min(1.0, quality))
        config = self._config["group_conversation"]
        return replace(
            current,
            familiarity=min(ceiling, current.familiarity + float(config["familiarity_delta"])),
            belonging=min(ceiling, current.belonging + max(0.0, quality) * float(config["belonging_quality_multiplier"])),
            affinity=max(-ceiling, min(ceiling, current.affinity + quality * float(config["affinity_quality_multiplier"]))),
            activity_willingness=max(0.0, min(ceiling, current.activity_willingness + quality * float(config["activity_quality_multiplier"]))),
        )

    # 生成联系人摘要
    def summarize_person(self, relationship: PersonRelationship) -> str:
        config = self._config["summary"]
        familiarity = (
            config["familiarity_high_text"]
            if relationship.familiarity >= float(config["familiarity_high_threshold"])
            else config["familiarity_medium_text"]
            if relationship.familiarity >= float(config["familiarity_medium_threshold"])
            else config["familiarity_low_text"]
        )
        affinity = (
            config["affinity_high_text"]
            if relationship.affinity >= float(config["affinity_high_threshold"])
            else config["affinity_positive_text"]
            if relationship.affinity >= float(config["affinity_positive_threshold"])
            else config["affinity_negative_text"]
            if relationship.affinity < float(config["affinity_negative_threshold"])
            else config["affinity_neutral_text"]
        )
        trust = (
            config["trust_high_text"]
            if relationship.trust >= float(config["trust_high_threshold"])
            else config["trust_medium_text"]
            if relationship.trust >= float(config["trust_medium_threshold"])
            else config["trust_low_text"]
        )
        return Template(str(config["template"])).substitute(
            familiarity=familiarity,
            affinity=affinity,
            trust=trust,
        )
