
from __future__ import annotations

from shared.contracts.live import InteractionEvent


class DeterministicDirectorPolicy:
    def __init__(self, actors: list[str]) -> None:
        self._actors = [actor for actor in actors if actor]
        self._cursor = 0

    @property
    def actors(self) -> tuple[str, ...]:
        return tuple(self._actors)

    def choose(self, event: InteractionEvent) -> str:
        if event.ai_target and event.ai_target in self._actors:
            return event.ai_target
        if not self._actors:
            return ""
        actor = self._actors[self._cursor % len(self._actors)]
        self._cursor += 1
        return actor
