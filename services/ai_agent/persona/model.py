from __future__ import annotations

import logging

from shared.contracts.social import ChatType

logger = logging.getLogger("ailove.ai-agent.persona")

class Persona:

    def __init__(self, ai_id: str, data: dict, gcfg, data_dir: str = "/app/data") -> None:
        self.ai_id = ai_id
        self._data = data
        self._gcfg = gcfg
        self._data_dir = data_dir

    @classmethod
    def from_definition(cls, definition, gcfg) -> "Persona":
        data = {
            "name": definition.name,
            "personality": definition.personality,
            "llm": {"models": definition.model_config},
        }
        return cls(
            definition.ai_id,
            data,
            gcfg,
            data_dir=f"/app/data/agents/{definition.ai_id}",
        )

    @property
    def name(self) -> str:
        return self._data.get("name", "__AILOVE_AI_NAME__")

    @property
    def traits(self) -> list[str]:
        return self._data.get("personality", {}).get("traits", [])

    @property
    def speaking_style(self) -> str:
        return self._data.get("personality", {}).get("speaking_style", "?????")

    @property
    def llm_models(self) -> dict:
        return self._data.get("llm", {}).get("models", {})

    def name_for(self, user_id: str) -> str:
        try:
            return self._gcfg.get("social", "contact_names", {}).get(user_id, "")
        except Exception:
            return ""

    async def should_respond(self, chat_type: str, to_ai: bool, at_user_id: str, ai_id: str, chat_id: str = "", join_checker=None) -> bool:
        if chat_type == ChatType.PRIVATE.value:
            return True
        if to_ai or (at_user_id and at_user_id == ai_id):
            return True
        if join_checker is not None:
            return await join_checker(chat_id)
        return False

