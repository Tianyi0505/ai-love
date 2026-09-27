from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

ConfigListener = Callable[[str, dict], Awaitable[None]]
Unsubscribe = Callable[[], Awaitable[None]]


class ConfigurationError(RuntimeError):
    """Configuration failure with a message that never includes document contents."""


class ConfigProvider(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> dict: ...

    @abstractmethod
    async def watch(self, key: str, callback: ConfigListener) -> Unsubscribe: ...

    @abstractmethod
    async def close(self) -> None: ...
