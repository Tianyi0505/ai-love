from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

MemoryOwnerType = Literal["person", "self"]
MemoryType = Literal[
    "observation",
    "fact",
    "belief",
    "feeling",
    "episodic",
    "procedural",
    "commitment",
]


class MemoryAtomOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_type: MemoryOwnerType
    type: MemoryType
    content: str
    importance: float
    confidence: float


class MemoryExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_summary: str
    memories: list[MemoryAtomOutput]


class MemoryConsolidationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str
