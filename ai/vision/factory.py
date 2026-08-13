from __future__ import annotations

from ai.vision.provider import VisionProvider
from ai.vision.providers import anthropic as _anthropic
from ai.vision.registry import provider_registry


# 创建视觉
def create_vision(kind: str, **opts) -> VisionProvider:
    cls = provider_registry.get(kind)
    return cls(**opts)
