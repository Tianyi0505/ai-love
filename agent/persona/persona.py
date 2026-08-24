from __future__ import annotations

import logging

from shared.configuration.global_settings import SocialSettings
from shared.contracts.agent import AgentDefinition, ModelSelectionConfig, PersonalityConfig
from shared.contracts.social import ChatType

logger = logging.getLogger("ailove.ai-agent.persona")


# 封装人格相关数据与行为
class Persona:
    # 初始化当前实例
    def __init__(
        self,
        ai_id: str,
        name: str,
        personality: PersonalityConfig,
        model_profile: ModelSelectionConfig,
        social_settings: SocialSettings,
    ) -> None:
        self.ai_id = ai_id
        self._name = name
        self._personality = personality
        self._model_profile = model_profile
        self._social_settings = social_settings

    # 从定义创建实例
    @classmethod
    def from_definition(cls, definition: AgentDefinition, social_settings: SocialSettings) -> "Persona":
        return cls(
            definition.ai_id,
            definition.name,
            definition.personality,
            definition.model_profile,
            social_settings,
        )

    # 返回名称
    @property
    def name(self) -> str:
        return self._name

    # 返回性格特征
    @property
    def traits(self) -> list[str]:
        return self._personality.traits

    # 返回说话风格
    @property
    def speaking_style(self) -> str:
        return self._personality.speaking_style

    # 返回大模型配置
    @property
    def llm_models(self):
        return self._model_profile

    # 获取用户显示名称
    def name_for(self, user_id: str) -> str:
        return self._social_settings.contact_names.get(user_id, "")

    # 判断是否需要回复
    def should_respond_directly(self, chat_type: str, to_ai: bool, at_user_id: str, ai_id: str) -> bool:
        if chat_type == ChatType.PRIVATE.value:
            return True
        if to_ai or (at_user_id and at_user_id == ai_id):
            return True
        return False
