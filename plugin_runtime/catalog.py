from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import Plugin, PluginError, PluginManifest


@dataclass(frozen=True)
class CatalogEntry:
    manifest: PluginManifest
    source: Path

    def create(self) -> Plugin:
        module, name = self.manifest.entrypoint.split(":")
        factory = getattr(importlib.import_module(module), name)
        instance = factory()
        if not isinstance(instance, Plugin):
            raise PluginError(f"{self.manifest.id} 未实现 Plugin 契约", "invalid")
        return instance


class PluginCatalog:
    """Read declarative local manifests without importing vendor dependencies."""

    def __init__(self, roots: list[Path], host: str) -> None:
        self.roots = roots
        self.host = host
        self.entries: dict[str, CatalogEntry] = {}
        self.errors: list[dict[str, str]] = []

    def refresh(self) -> None:
        candidates = {}
        errors = []
        duplicates = set()
        for root in self.roots:
            for path in sorted(root.glob("*/plugin.json")):
                try:
                    manifest = PluginManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
                except (ValueError, OSError) as exc:
                    errors.append({"source": path.parent.name, "error": f"清单读取失败：{type(exc).__name__}"})
                    continue
                if manifest.host != self.host:
                    continue
                if manifest.id in candidates or manifest.id in duplicates:
                    candidates.pop(manifest.id, None)
                    duplicates.add(manifest.id)
                    errors.append({"source": path.parent.name, "error": f"重复插件标识：{manifest.id}"})
                    continue
                if len(set(manifest.provides)) != len(manifest.provides):
                    errors.append({"source": path.parent.name, "error": f"重复能力声明：{manifest.id}"})
                    continue
                candidates[manifest.id] = CatalogEntry(manifest, path)
        self.entries = candidates
        self.errors = errors
