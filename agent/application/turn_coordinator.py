from __future__ import annotations

import asyncio


# 按会话串行化轮次执行
class TurnCoordinator:
    # 初始化当前实例
    def __init__(self, max_locks: int = 1024) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._max_locks = max_locks

    # 返回会话串行化锁
    def lock_for(self, conversation_key: str) -> asyncio.Lock:
        lock = self._locks.get(conversation_key)
        if lock is None:
            if len(self._locks) >= self._max_locks:
                stale = [
                    key
                    for key, item in self._locks.items()
                    if not item.locked()
                ][: self._max_locks // 2]
                for key in stale:
                    self._locks.pop(key, None)
            lock = self._locks.setdefault(conversation_key, asyncio.Lock())
        return lock
