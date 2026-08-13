
from __future__ import annotations

from typing import Protocol

from shared.contracts.events import TurnRequest, make_conversation_id
from shared.contracts.social import SocialMessage


# 定义归属解析器接口
class OwnershipResolver(Protocol):
    # 获取社交账号所属智能体
    async def owner_for_social_account(self, account_id: str) -> str | None: ...


# 按静态配置解析账号归属
class StaticOwnershipResolver:

    # 初始化当前实例
    def __init__(self, owners: dict[str, str]) -> None:
        self._owners = dict(owners)

    # 获取社交账号所属智能体
    async def owner_for_social_account(self, account_id: str) -> str | None:
        return self._owners.get(account_id)


# 路由社交消息与发送请求
class SocialRouter:
    # 初始化当前实例
    def __init__(self, ownership: OwnershipResolver) -> None:
        self._ownership = ownership

    # 获取账号所属智能体
    async def owner_for(self, account_id: str) -> str | None:
        return await self._ownership.owner_for_social_account(account_id)

    # 路由消息
    async def route(self, message: SocialMessage) -> TurnRequest:
        ai_id = await self._ownership.owner_for_social_account(message.account_id)
        if not ai_id:
            raise LookupError(f"社交账号尚未绑定 AI: {message.account_id}")
        conversation_id = message.meta.get("conversation_id") or make_conversation_id(
            message.platform,
            message.account_id,
            message.chat.chat_id,
        )
        return TurnRequest(
            ai_id=ai_id,
            account_id=message.account_id,
            conversation_id=conversation_id,
            source="social",
            input_text=message.text,
            chat_type=message.chat.chat_type.value,
            person_id=message.meta.get("person_id", ""),
            platform_identity_id=message.meta.get("platform_identity_id", ""),
            metadata={"social_message": message.to_dict()},
        )
