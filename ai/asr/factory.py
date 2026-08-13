from __future__ import annotations

from ai.asr.provider import ASRProvider
from ai.asr.registry import provider_registry


# 创建语音识别
def create_asr(kind: str, **options) -> ASRProvider:
    provider_type = provider_registry.get(kind)
    return provider_type(**options)
