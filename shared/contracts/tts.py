from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_id: str
    text: str


class SynthesizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_path: str
    duration_sec: float
