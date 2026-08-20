from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MusicToolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    title: str
    description: str
    action_description: str
    query_description: str
    volume_description: str
    volume_min: int
    volume_max: int
    adapter_note: str
