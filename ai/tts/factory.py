from __future__ import annotations

from ai.tts.provider import TTSProvider
from ai.tts.providers import gptsovits as _gptsovits
from ai.tts.registry import provider_registry
from ai.tts.routing import TTSRouter


# 创建语音合成
def create_tts(tts_config: dict, ai_id: str, timeout_sec: float) -> TTSProvider:
    providers: list[TTSProvider] = []
    for entry in tts_config["providers"]:
        opts = {key: value for key, value in entry.items() if key != "provider"}
        cls = provider_registry.get(entry["provider"])
        providers.append(cls(ai_id=ai_id, timeout_sec=timeout_sec, **opts))
    return TTSRouter(providers)
