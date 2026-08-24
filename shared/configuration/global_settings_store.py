from __future__ import annotations

from shared.configuration.global_settings import GlobalSettings
from shared.infrastructure.service_config import ConfigProvider


class GlobalSettingsStore:
    def __init__(self, provider: ConfigProvider) -> None:
        self._provider = provider
        self._settings: GlobalSettings | None = None

    async def load(self) -> GlobalSettings:
        self._settings = GlobalSettings.model_validate(await self._provider.get("ailove.config"))
        await self._provider.watch("ailove.config", self._on_change)
        return self.settings

    @property
    def settings(self) -> GlobalSettings:
        if self._settings is None:
            raise RuntimeError("全局配置尚未加载")
        return self._settings

    async def _on_change(self, data_id: str, parsed: dict) -> None:
        self._settings = GlobalSettings.model_validate(parsed)
