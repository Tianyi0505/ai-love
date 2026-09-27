from __future__ import annotations

from importlib.metadata import entry_points

from plugin_runtime import Plugin, PluginError

from .components import load_symbol


class FactoryRegistry:
    """Lazy strategy lookup: only the selected implementation imports its dependencies."""

    def __init__(self, implementations: dict[str, str], group: str | None = None) -> None:
        self._implementations = dict(implementations)
        if group:
            for entry in entry_points(group=group):
                previous = self._implementations.get(entry.name)
                if previous and previous != entry.value:
                    raise PluginError(f"重复工厂：{entry.name}")
                self._implementations[entry.name] = entry.value

    def create(self, name: str, *args, **kwargs):
        reference = self._implementations.get(name)
        if reference is None:
            raise PluginError(f"未安装能力实现：{name}", "unavailable")
        return load_symbol(reference)(*args, **kwargs)


class FactoryPlugin(Plugin):
    async def start(self) -> None:
        registry = FactoryRegistry(
            dict(self.context.config.get("implementations", {})), self.context.config.get("entrypoint_group")
        )
        for capability in self.context.manifest.provides:
            self.context.provide(capability, registry)


class ModelFactoryPlugin(Plugin):
    async def start(self) -> None:
        from functools import partial

        from shared.chat_model_factory import create_chat_model

        strategies = FactoryRegistry(dict(self.context.config["implementations"]), "ai_love.chat_models")
        self.context.provide("model.factory", partial(create_chat_model, strategies=strategies))
