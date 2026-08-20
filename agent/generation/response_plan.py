from __future__ import annotations

from typing import Literal

from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, field_validator

_MARKDOWN = MarkdownIt()


class Speech(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    delivery: Literal["text", "voice", "live"]

    @field_validator("text")
    @classmethod
    def require_plain_text(cls, value: str) -> str:
        tokens = _MARKDOWN.parse(value)
        inline_children = [child.type for token in tokens if token.type == "inline" for child in (token.children or [])]
        if any(token_type not in {"text", "softbreak"} for token_type in inline_children):
            raise ValueError("speech.text 必须是纯文本")
        return value


class Emotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["neutral", "happy", "sad", "angry", "surprised"]
    intensity: float


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sticker"]
    query: str


class ResponsePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speech: list[Speech]
    emotion: Emotion
    actions: list[Action]

    @property
    def text(self) -> str:
        return "".join(item.text for item in self.speech)


class ParticipationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participate: bool
    reason: str
