from __future__ import annotations

import time
from dataclasses import dataclass, field


# 表示记忆活动数据
@dataclass(frozen=True)
class MemoryActivity:
    ai_id: str
    person_id: str
    conversation_id: str
    message_id: str
    sequence: int
    active_at: float = field(default_factory=time.time)

    # 转换为字典
    def to_dict(self) -> dict:
        return {
            "ai_id": self.ai_id,
            "person_id": self.person_id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "sequence": self.sequence,
            "active_at": self.active_at,
        }

    # 从字典创建实例
    @classmethod
    def from_dict(cls, data: dict) -> "MemoryActivity":
        return cls(
            ai_id=str(data.get("ai_id") or ""),
            person_id=str(data.get("person_id") or ""),
            conversation_id=str(data.get("conversation_id") or ""),
            message_id=str(data.get("message_id") or ""),
            sequence=int(data.get("sequence") or 0),
            active_at=float(data.get("active_at") or time.time()),
        )
