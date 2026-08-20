from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = ""
    ai_id: str = ""
    account_id: str = ""
    conversation_id: str = ""
    platform: str = ""
    chat_type: str = ""
    chat_id: str = ""
    sender_person_id: str = ""

    @property
    def is_group(self) -> bool:
        return self.chat_type == "group"
