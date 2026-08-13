
from __future__ import annotations

DEFAULTS: dict = {
    "qq": {
        "whitelist": [],
        "space_interval_sec": 3600,
        "space_reply_prob": 0.5,
    },
    "sticker": {
        "capacity": 50,
        "half_life_sec": 2592000,
        "boost_delta": 10.0,
        "threshold": 20.0,
        "collect_min_quality": 0.65,
    },
    "social": {
        "join_prob": 0.3,
        "join_cooldown_sec": 60,
        "send_timeout_sec": 15,
    },
    "llm": {
        "timeout_ms": 60000,
    },
}


class GlobalConfig:

    def __init__(self, provider=None) -> None:
        self._provider = provider
        self._data: dict = {}

    async def load(self) -> None:
        if self._provider is None:
            self._data = DEFAULTS
            return
        try:
            data = await self._provider.get("ailove.config")
            self._data = data or {}
        except Exception:
            self._data = {}
        await self._subscribe()

    async def _subscribe(self) -> None:
        if self._provider is None or getattr(self, "_watching", False):
            return
        self._watching = True

        async def _on_change(data_id: str, parsed: dict) -> None:
            self._data = parsed or {}

        await self._provider.watch("ailove.config", _on_change)

    def get(self, section: str, key: str, default=None):
        if section in self._data and key in self._data[section]:
            return self._data[section][key]
        return DEFAULTS.get(section, {}).get(key, default)

    def section(self, name: str) -> dict:
        merged = dict(DEFAULTS.get(name, {}))
        merged.update(self._data.get(name, {}))
        return merged
