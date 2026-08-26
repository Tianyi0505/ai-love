from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.snowflake_id_generator import snowflake_ids


class InteractionType(str, Enum):
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


class LiveContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Viewer(LiveContract):
    uid: int
    name: str
    title: str = ""


class InteractionEvent(LiveContract):
    type: InteractionType
    actor: Viewer
    importance: int
    content: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    ai_target: str = ""
    context_metadata: dict[str, Any] = Field(default_factory=dict)
    event_id: str = Field(default_factory=lambda: str(snowflake_ids().next_id()))
    timestamp: int = Field(default_factory=lambda: time.time_ns() // 1_000_000)
