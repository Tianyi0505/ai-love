
from __future__ import annotations

from abc import ABC
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
    def set_message_handler(self, handler) -> None:
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

    # 返回渠道能力
    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(channel=self.name)


# 创建渠道
def create_channel(kind: str, cfg: dict) -> Channel:
    cls = channel_registry.get(kind)
    return cls(cfg)
