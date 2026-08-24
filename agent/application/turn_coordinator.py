from __future__ import annotations

import asyncio
from weakref import WeakValueDictionary


# 按会话串行化轮次执行
class TurnCoordinator:
    def __init__(self) -> None:
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    # 返回会话串行化锁
    def lock_for(self, conversation_key: str) -> asyncio.Lock:
        lock = self._locks.get(conversation_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[conversation_key] = lock
        return lock
