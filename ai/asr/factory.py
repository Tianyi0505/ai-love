from __future__ import annotations

from ai.asr.provider import ASRProvider
from ai.asr.registry import provider_registry


def create_asr(kind: str, **options) -> ASRProvider:
    provider_type = provider_registry.get(kind)
    return provider_type(**options)
