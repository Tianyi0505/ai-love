from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any


class ResourceScope:
    """Own tasks and finalizers; fence new callbacks before draining existing work."""

    def __init__(self) -> None:
        self.accepting = True
        self._active = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._tasks: set[asyncio.Task] = set()
        self._finalizers: list[Callable] = []
        self._quiescers: list[Callable] = []
        self.failures: list[str] = []

    @property
    def active_calls(self) -> int:
        return self._active

    def defer(self, callback: Callable) -> None:
        self._finalizers.append(callback)

    def on_quiesce(self, callback: Callable) -> None:
        self._quiescers.append(callback)

    def spawn(self, coroutine: Awaitable, *, name: str | None = None) -> asyncio.Task:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.failures.append(type(task.exception()).__name__)
            self.failures[:] = self.failures[-16:]

    @asynccontextmanager
    async def call(self):
        if not self.accepting:
            raise RuntimeError("插件正在停用，暂不接受新工作")
        self._active += 1
        self._idle.clear()
        try:
            yield
        finally:
            self._active -= 1
            if not self._active:
                self._idle.set()

    def guard(self, callback: Callable) -> Callable:
        async def guarded(*args, **kwargs):
            async with self.call():
                return await callback(*args, **kwargs)

        return guarded

    async def quiesce(self) -> None:
        self.accepting = False
        await self._run_all(self._quiescers)

    async def drain(self) -> None:
        await self._idle.wait()

    async def close(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        await self._run_all(self._finalizers)

    @staticmethod
    async def _run_all(callbacks) -> None:
        errors = []
        for callback in list(reversed(callbacks)):
            try:
                result: Any = callback()
                if inspect.isawaitable(result):
                    await result
                callbacks.remove(callback)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("插件资源回收失败", errors)
