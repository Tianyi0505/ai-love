from __future__ import annotations

from dataclasses import dataclass, field


# 表示人物候选
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


# 表示一条人物指代（认知状态 + 证据）
@dataclass(frozen=True)
class EntityReference:
    text: str
    status: str = "unresolved"
    person_id: str = ""
    display_name: str = ""
    candidates: tuple[EntityCandidate, ...] = ()
    evidence: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        data: dict = {"text": self.text, "status": self.status}
        if self.person_id:
            data["person_id"] = self.person_id
        if self.display_name:
            data["display_name"] = self.display_name
        if self.evidence:
            data["evidence"] = list(self.evidence)
        if self.candidates:
            data["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return data


# 表示当前语境的人物证据集合
@dataclass(frozen=True)
class EntityContext:
    current_sender: dict = field(default_factory=dict)
    references: tuple[EntityReference, ...] = ()
    recent_participants: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "current_sender": dict(self.current_sender),
            "references": [reference.to_dict() for reference in self.references],
            "recent_participants": [dict(item) for item in self.recent_participants],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "EntityContext":
        raw = data if isinstance(data, dict) else {}
        return cls(
            current_sender=dict(raw.get("current_sender") or {}),
            references=tuple(
                EntityReference(
                    text=str(item.get("text") or ""),
                    status=str(item.get("status") or "unresolved"),
                    person_id=str(item.get("person_id") or ""),
                    display_name=str(item.get("display_name") or ""),
                    candidates=tuple(
                        EntityCandidate(
                            person_id=str(candidate.get("person_id") or ""),
                            display_name=str(candidate.get("display_name") or ""),
                            confidence=float(candidate.get("confidence") or 0.0),
                            evidence=tuple(candidate.get("evidence") or []),
                        )
                        for candidate in item.get("candidates") or []
                        if isinstance(candidate, dict)
                    ),
                    evidence=tuple(item.get("evidence") or []),
                )
                for item in raw.get("references") or []
                if isinstance(item, dict)
            ),
            recent_participants=tuple(
                dict(item) for item in raw.get("recent_participants") or [] if isinstance(item, dict)
            ),
        )
