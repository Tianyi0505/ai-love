from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shared.contracts.rpc.social import SocialSendRequest, SocialSendResponse
from shared.contracts.social import SocialMessage


# 描述渠道支持的发送能力
@dataclass
class ChannelCapabilities:
    channel: str
    send_types: list[str]
    receive_types: list[str]
    supports_history: bool
    is_live_platform: bool
    supports_multi_ai: bool


# 定义渠道接口
class Channel(ABC):
    name: str
    _on_message: Callable[[SocialMessage], Awaitable[None]] | None = None

    # 初始化当前实例
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.account_id = str(cfg["account_id"])
        self._on_message = None

    # 启动服务
    @abstractmethod
    async def start(self) -> None: ...

    # 停止服务
    @abstractmethod
    async def stop(self) -> None: ...

    # 设置消息处理器
    def set_message_handler(self, handler: Callable[[SocialMessage], Awaitable[None]]) -> None:
        self._on_message = handler

    @property
    def message_handler(self) -> Callable[[SocialMessage], Awaitable[None]]:
        if self._on_message is None:
            raise RuntimeError(f"渠道 {self.name} 未配置消息处理器")
        return self._on_message

    # 发送消息
    @abstractmethod
    async def send(self, request: SocialSendRequest) -> SocialSendResponse: ...

    # 补全消息内容
    @abstractmethod
    async def hydrate_message(self, message: SocialMessage) -> SocialMessage: ...

    # 列出当前群成员快照
    @abstractmethod
    async def list_group_members(self, chat_id: str) -> list[dict]: ...

    @abstractmethod
    async def list_contacts(self, timeout_sec: float) -> dict[str, str]: ...

    # 返回渠道能力
    @property
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities: ...
