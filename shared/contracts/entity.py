from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityCandidate:
    person_id: str
    display_name: str = ""
    confidence: float = 0.0
    evidence: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "person_id": self.person_id,
            "display_name": self.display_name,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


# 表示当前语境的人物证据集合
@dataclass(frozen=True)
class EntityContext:
    mentions: tuple[dict, ...] = ()
    recent_participants: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "mentions": [dict(item) for item in self.mentions],
            "recent_participants": [dict(item) for item in self.recent_participants],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "EntityContext":
        raw = data if isinstance(data, dict) else {}
        return cls(
            mentions=tuple(dict(item) for item in raw.get("mentions") or [] if isinstance(item, dict)),
            recent_participants=tuple(
                dict(item) for item in raw.get("recent_participants") or [] if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True)
class EntityMention:
    text: str
    resolution_type: str
    confidence: float
    person_id: str = ""
    candidates: tuple[EntityCandidate, ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> bool:
        return bool(self.person_id)

    def to_dict(self) -> dict:
        return {
            "status": "resolved" if self.resolved else "unresolved",
            "text": self.text,
            "person_id": self.person_id or None,
            "resolution_type": self.resolution_type,
            "confidence": self.confidence,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }
