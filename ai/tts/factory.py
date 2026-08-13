from __future__ import annotations

from ai.tts.provider import TTSProvider
from ai.tts.registry import provider_registry


def create_tts(kind: str, **options) -> TTSProvider:
    provider_type = provider_registry.get(kind)
    return provider_type(**options)
