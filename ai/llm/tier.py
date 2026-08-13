
from __future__ import annotations

from enum import Enum


# 定义模型档位枚举
class Tier(str, Enum):

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


# 定义模型能力枚举
class ModelCapability(str, Enum):

    CHAT = "chat"
    EMBEDDING = "embedding"
