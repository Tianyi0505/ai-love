
from __future__ import annotations

from enum import Enum


class Tier(str, Enum):

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


class ModelCapability(str, Enum):

    CHAT = "chat"
    EMBEDDING = "embedding"
