
from __future__ import annotations

from abc import ABC, abstractmethod

from shared.infrastructure.registry import Registry

skill_registry = Registry("skill")


class BaseSkill(ABC):

    info: dict = {
        "description": "",
        "parameters": {"type": "object", "properties": {}},
    }
    is_heavy: bool = False

    async def execute(self, args: dict) -> str:
        error = await self._validate(args)
        if error:
            return error
        raw = await self._do_execute(args)
        return await self._format_result(raw, args)

    @abstractmethod
    async def _do_execute(self, args: dict) -> object:
        pass

    async def _validate(self, args: dict) -> str:
        return ""

    async def _format_result(self, raw: object, args: dict) -> str:
        return str(raw)


def create_skill(name: str) -> BaseSkill:
    cls = skill_registry.get(name)
    return cls()
