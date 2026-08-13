from __future__ import annotations

from shared.vision import default as _default
from shared.vision.registry import describer_registry
from shared.vision.types import ImageDescriber


def create_describer(kind: str, **opts) -> ImageDescriber:
    cls = describer_registry.get(kind)
    return cls(**opts)
