from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class NapCatSegment(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    data: dict[str, Any]


class NapCatSender(BaseModel):
    model_config = ConfigDict(extra="allow")

    nickname: str
    card: str | None = None
    role: str | None = None


class NapCatMessageEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    post_type: str | None = None
    message_type: str
    message: list[NapCatSegment]
    user_id: str | int
    sender: NapCatSender
    message_id: str | int
    time: int
    group_id: str | int | None = None
    group_name: str | None = None
