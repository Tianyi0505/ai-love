from __future__ import annotations

from ai.vision.provider import VisionProvider
from ai.vision.providers import anthropic as _anthropic
from ai.vision.providers import openai_compat as _openai_compat
from ai.vision.registry import provider_registry
from ai.vision.routing import VisionRouter


# 创建视觉
def create_vision(image_config: dict) -> VisionProvider:
    shared = {key: value for key, value in image_config.items() if key != "providers"}
    providers: list[VisionProvider] = []
    for entry in image_config["providers"]:
        opts = dict(entry)
        opts.pop("provider", None)
        cls = provider_registry.get(entry["provider"])
        providers.append(cls(**shared, **opts))
    return VisionRouter(providers, shared.get("fallbacks", {}))
