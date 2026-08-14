
from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from shared.contracts.social import Chat, SocialMessage
from shared.infrastructure.registry import Registry

channel_registry = Registry("channel")


# 描述渠道支持的发送能力
@dataclass
class ChannelCapabilities:
    channel: str
    send_types: list[str] = field(default_factory=list)
    receive_types: list[str] = field(default_factory=list)
    supports_history: bool = False
    is_live_platform: bool = False
    supports_multi_ai: bool = False


# 定义渠道接口
class Channel(ABC):

    name: str = ""
    _on_message: Callable[[SocialMessage], Awaitable[None]] | None = None

    # 初始化当前实例
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.account_id = str(cfg["account_id"])
        self._on_message = None

    # 启动服务
    async def start(self) -> None: ...

    # 停止服务
    async def stop(self) -> None: ...

    # 设置消息处理器
    def set_message_handler(self, handler: Callable[[SocialMessage], Awaitable[None]] | None) -> None:
        if handler is not None and not callable(handler):
            raise TypeError(f"消息处理器必须是可调用对象: {type(handler).__name__}")
        self._on_message = handler

    # 发送消息
    async def send(self, req) -> dict:
        raise NotImplementedError

    # 列出历史
    async def list_history(
        self,
        chat: Chat,
        since: int,
        limit: int,
    ) -> list[SocialMessage]:
        return []

    # 补全消息内容
    async def hydrate_message(self, message: SocialMessage) -> SocialMessage:
        return message

    # 列出当前群成员快照
    async def list_group_members(self, chat_id: str) -> list[dict]:
        return []

    # 返回渠道能力
    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(channel=self.name)


# 创建渠道
def create_channel(kind: str, cfg: dict) -> Channel:
    cls = channel_registry.get(kind)
    return cls(cfg)
