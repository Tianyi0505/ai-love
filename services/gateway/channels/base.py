
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from shared.contracts.social import Chat, SocialMessage
from shared.infrastructure.registry import Registry

channel_registry = Registry("channel")


@dataclass
class ChannelCapabilities:
    channel: str
    send_types: list[str] = field(default_factory=list)
    receive_types: list[str] = field(default_factory=list)
    supports_history: bool = False
    is_live_platform: bool = False
    supports_multi_ai: bool = False


class Channel(ABC):

    name: str = ""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.account_id = str(cfg.get("account_id", ""))
        self._on_message = None

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def set_message_handler(self, handler) -> None:
        self._on_message = handler

    async def send(self, req) -> dict:
        raise NotImplementedError

    async def list_history(
        self,
        chat: Chat,
        since: int = 0,
        limit: int = 50,
    ) -> list[SocialMessage]:
        return []

    async def hydrate_message(self, message: SocialMessage) -> SocialMessage:
        return message

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(channel=self.name)


def create_channel(kind: str, cfg: dict) -> Channel:
    cls = channel_registry.get(kind)
    return cls(cfg)  # type: ignore
