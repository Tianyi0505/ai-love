
from __future__ import annotations

from shared.infrastructure.runtime_config import required_config


class GlobalConfig:

    def __init__(self, provider) -> None:
        self._provider = provider
        self._data: dict = {}

    async def load(self) -> None:
        data = await self._provider.get("ailove.config")
        if not data:
            raise RuntimeError("Nacos 缺少配置: ailove.config")
        self._data = data
        await self._subscribe()

    async def _subscribe(self) -> None:
        if getattr(self, "_watching", False):
            return
        self._watching = True

        async def _on_change(data_id: str, parsed: dict) -> None:
            if not parsed:
                raise RuntimeError("Nacos 配置 ailove.config 不能为空")
            self._data = parsed

        await self._provider.watch("ailove.config", _on_change)

    def get(self, section: str, key: str):
        values = self.section(section)
        return required_config(values, key, f"ailove.config.{section}.{key}")

    def section(self, name: str) -> dict:
        values = required_config(self._data, name, f"ailove.config.{name}")
        if not isinstance(values, dict):
            raise RuntimeError(f"ailove.config.{name} 必须是对象")
        return values
