from __future__ import annotations

from ai.tts.provider import TTSProvider
from ai.tts.registry import provider_registry


# 创建语音合成
def create_tts(kind: str, **options) -> TTSProvider:
    provider_type = provider_registry.get(kind)
    return provider_type(**options)
