
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PersonRelationship:
    familiarity: float = 0.0
    affinity: float = 0.0
    trust: float = 0.0
    importance: float = 0.0


@dataclass(frozen=True)
class GroupRelationship:
    familiarity: float = 0.0
    belonging: float = 0.0
    affinity: float = 0.0
    activity_willingness: float = 0.0


@dataclass(frozen=True)
class RelationshipCeilings:
    default: float = 0.7
    person_whitelist: frozenset[str] = frozenset()
    group_whitelist: frozenset[str] = frozenset()

    def person(self, person_id: str) -> float:
        return 1.0 if person_id in self.person_whitelist else self.default

    def group(self, group_id: str) -> float:
        return 1.0 if group_id in self.group_whitelist else self.default


class RelationshipPolicy:

    def __init__(self, ceilings: RelationshipCeilings | None = None) -> None:
        self._ceilings = ceilings or RelationshipCeilings()

    def on_conversation(
        self,
        person_id: str,
        current: PersonRelationship,
        quality: float = 0.0,
    ) -> PersonRelationship:
        ceiling = self._ceilings.person(person_id)
        quality = max(-1.0, min(1.0, quality))
        return replace(
            current,
            familiarity=min(ceiling, current.familiarity + 0.02),
            affinity=max(-ceiling, min(ceiling, current.affinity + quality * 0.02)),
        )

    def on_gift(
        self,
        person_id: str,
        current: PersonRelationship,
        amount: float,
    ) -> PersonRelationship:

        ceiling = self._ceilings.person(person_id)
        familiarity_delta = min(0.03, max(0.0, amount) / 10000.0)
        importance_delta = min(0.05, max(0.0, amount) / 5000.0)
        return replace(
            current,
            familiarity=min(ceiling, current.familiarity + familiarity_delta),
            importance=min(ceiling, current.importance + importance_delta),
        )

    def on_trust_event(
        self,
        person_id: str,
        current: PersonRelationship,
        positive: bool,
    ) -> PersonRelationship:
        ceiling = self._ceilings.person(person_id)
        delta = 0.02 if positive else -0.08
        return replace(current, trust=max(0.0, min(ceiling, current.trust + delta)))

    def on_group_conversation(
        self,
        group_id: str,
        current: GroupRelationship,
        quality: float = 0.0,
    ) -> GroupRelationship:
        ceiling = self._ceilings.group(group_id)
        quality = max(-1.0, min(1.0, quality))
        return replace(
            current,
            familiarity=min(ceiling, current.familiarity + 0.02),
            belonging=min(ceiling, current.belonging + max(0.0, quality) * 0.01),
            affinity=max(-ceiling, min(ceiling, current.affinity + quality * 0.02)),
            activity_willingness=max(0.0, min(ceiling, current.activity_willingness + quality * 0.02)),
        )

    @staticmethod
    def summarize_person(relationship: PersonRelationship) -> str:
        familiarity = "很熟悉" if relationship.familiarity >= 0.7 else "熟悉" if relationship.familiarity >= 0.3 else "还不熟悉"
        affinity = "很喜欢" if relationship.affinity >= 0.6 else "有好感" if relationship.affinity >= 0.2 else "有些反感" if relationship.affinity < -0.2 else "态度平常"
        trust = "高度信任" if relationship.trust >= 0.7 else "逐渐信任" if relationship.trust >= 0.3 else "尚未建立充分信任"
        return f"你对对方{familiarity}，{affinity}，并且{trust}。"
