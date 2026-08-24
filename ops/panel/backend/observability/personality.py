from __future__ import annotations

from .schemas import PersonalityResponse


class PersonalityReader:
    """只负责读取 Nacos 中的生效人格定义。"""

    def __init__(self, agent_store) -> None:
        self._agent_store = agent_store

    async def read(self, ai_id: str) -> PersonalityResponse:
        definition = await self._agent_store.load(ai_id)
        personality = definition.personality
        return PersonalityResponse(
            ai_id=definition.ai_id,
            name=definition.name,
            identity=definition.identity,
            traits=[str(item) for item in personality["traits"]],
            speaking_style=str(personality["speaking_style"]),
            catchphrases=[str(item) for item in personality["catchphrases"]],
            taboos=[str(item) for item in personality["taboos"]],
            version=definition.version,
            fingerprint=definition.fingerprint,
        )
