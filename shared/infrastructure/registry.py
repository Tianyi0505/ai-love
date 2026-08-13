
from __future__ import annotations

from typing import Callable, Type, TypeVar

T = TypeVar("T")


class Registry:
    def __init__(self, namespace: str) -> None:
        self._namespace = namespace
        self._items: dict[str, type] = {}

    def register(self, name: str) -> Callable[[Type[T]], Type[T]]:

        def deco(cls: Type[T]) -> Type[T]:
            if name in self._items:
                raise ValueError(f"[{self._namespace}] 重复注册: {name!r}")
            self._items[name] = cls
            return cls

        return deco

    def get(self, name: str) -> type:
        if name not in self._items:
            raise KeyError(f"[{self._namespace}] 未注册: {name!r}。可用: {sorted(self._items)}")
        return self._items[name]

    def contains(self, name: str) -> bool:
        return name in self._items

    def names(self) -> list[str]:
        return list(self._items)

    def all(self) -> list[tuple[str, type]]:
        return list(self._items.items())
