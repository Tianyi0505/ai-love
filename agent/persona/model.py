from __future__ import annotations

import logging

from shared.contracts.social import ChatType

logger = logging.getLogger("ailove.ai-agent.persona")

# 封装人格相关数据与行为
class Persona:

    # 初始化当前实例
    def __init__(self, ai_id: str, data: dict, gcfg, data_dir: str) -> None:
        self.ai_id = ai_id
        self._data = data
        self._gcfg = gcfg
        self._data_dir = data_dir

    # 从定义创建实例
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

    # 返回名称
    @property
    def name(self) -> str:
        return self._data["name"]

    # 返回性格特征
    @property
    def traits(self) -> list[str]:
        return self._data["personality"]["traits"]

    # 返回说话风格
    @property
    def speaking_style(self) -> str:
        return self._data["personality"]["speaking_style"]

    # 返回大模型配置
    @property
    def llm_models(self) -> dict:
        return self._data["llm"]["models"]

    # 获取用户显示名称
    def name_for(self, user_id: str) -> str:
        return self._gcfg.get("social", "contact_names").get(user_id, "")

    # 判断是否需要回复
    async def should_respond(self, chat_type: str, to_ai: bool, at_user_id: str, ai_id: str, chat_id: str = "", join_checker=None) -> bool:
        if chat_type == ChatType.PRIVATE.value:
            return True
        if to_ai or (at_user_id and at_user_id == ai_id):
            return True
        if join_checker is not None:
            return await join_checker(chat_id)
        return False
