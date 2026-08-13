
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from shared.infrastructure.registry import Registry


class InteractionType(Enum):
    DANMAKU = "danmaku"
    GIFT = "gift"
    GUARD = "guard"
    ENTER = "enter"
    FOLLOW = "follow"
    SUPER_CHAT = "super_chat"
    RAFFLE = "raffle"
    LIVE_START = "live_start"
    LIVE_END = "live_end"


SUBJ_EVENT_AI = "ai.events.{ai_id}"
SUBJ_EVENT_ALL = "ai.events.all"
SUBJ_SPEECH = "ai.speech.request"
SUBJ_AVATAR = "avatar.command.{ai_id}"
SUBJ_MUSIC = "music.command.{ai_id}"


@dataclass
class Viewer:
    uid: int
    name: str
    title: str = ""


@dataclass
class InteractionEvent:

    type: InteractionType
    actor: Viewer
    importance: int
    content: str = ""
    meta: dict = field(default_factory=dict)
    ai_target: str = ""
    context_metadata: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"{int(time.time() * 1000)}-{id(object())}")
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "actor": {"uid": self.actor.uid, "name": self.actor.name, "title": self.actor.title},
            "content": self.content,
            "meta": self.meta,
            "importance": self.importance,
            "ai_target": self.ai_target,
            "context_metadata": self.context_metadata,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionEvent":
        return cls(
            type=InteractionType(data["type"]),
            actor=Viewer(**data.get("actor", {})),
            content=data.get("content", ""),
            meta=data.get("meta", {}),
            importance=data["importance"],
            ai_target=data.get("ai_target", ""),
            context_metadata=data.get("context_metadata", {}),
            event_id=data.get("event_id", ""),
            timestamp=data.get("timestamp", 0),
        )


HandlerT = Callable[["InteractionEvent"], object]


class EventDispatcher:

    def __init__(self) -> None:
        self._handlers: dict[InteractionType, list[tuple[int, int, HandlerT]]] = {}

    def on(self, event_type: InteractionType, priority: int) -> Callable[[HandlerT], HandlerT]:

        def deco(fn: HandlerT) -> HandlerT:
            seq = len(self._handlers.get(event_type, []))
            self._handlers.setdefault(event_type, []).append((priority, seq, fn))
            self._handlers[event_type].sort(key=lambda x: (-x[0], x[1]))
            return fn

        return deco

    async def dispatch(self, evt: InteractionEvent) -> None:
        for _, _, handler in self._handlers.get(evt.type, []):
            result = handler(evt)
            if hasattr(result, "__await__"):
                await result
