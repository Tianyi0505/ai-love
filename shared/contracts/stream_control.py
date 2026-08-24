from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StreamControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
