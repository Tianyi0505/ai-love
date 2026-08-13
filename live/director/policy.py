
from __future__ import annotations

from shared.contracts.live import InteractionEvent


# 按固定顺序选择互动角色
class DeterministicDirectorPolicy:
    # 初始化当前实例
    def __init__(self, actors: list[str]) -> None:
        self._actors = [actor for actor in actors if actor]
        self._cursor = 0

    # 返回可选互动角色
    @property
    def actors(self) -> tuple[str, ...]:
        return tuple(self._actors)

    # 选择候选动作
    def choose(self, event: InteractionEvent) -> str:
        if event.ai_target and event.ai_target in self._actors:
            return event.ai_target
        if not self._actors:
            return ""
        actor = self._actors[self._cursor % len(self._actors)]
        self._cursor += 1
        return actor
