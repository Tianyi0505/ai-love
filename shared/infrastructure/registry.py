
from __future__ import annotations

from typing import Callable, Type, TypeVar

T = TypeVar("T")


# 注册并查询命名组件
class Registry:
    # 初始化当前实例
    def __init__(self, namespace: str) -> None:
        self._namespace = namespace
        self._items: dict[str, type] = {}

    # 注册组件
    def register(self, name: str) -> Callable[[Type[T]], Type[T]]:

        # 注册装饰器目标
        def deco(cls: Type[T]) -> Type[T]:
            if name in self._items:
                raise ValueError(f"[{self._namespace}] 重复注册: {name!r}")
            self._items[name] = cls
            return cls

        return deco

    # 获取数据
    def get(self, name: str) -> type:
        if name not in self._items:
            raise KeyError(f"[{self._namespace}] 未注册: {name!r}。可用: {sorted(self._items)}")
        return self._items[name]

    # 判断是否包含指定项
    def contains(self, name: str) -> bool:
        return name in self._items

    # 列出注册名称
    def names(self) -> list[str]:
        return list(self._items)

    # 列出全部数据
    def all(self) -> list[tuple[str, type]]:
        return list(self._items.items())
