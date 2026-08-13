
from __future__ import annotations

import asyncio

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from shared.contracts.social import ContentType, SocialMessage
from shared.infrastructure.registry import Registry

asr_registry = Registry("asr")


class ASREngine(ABC):

    @abstractmethod
    async def transcribe(self, audio_url: str) -> str:
        pass


class MessageUnderstanding:

    def __init__(self, asr: ASREngine | None = None, image_describer=None) -> None:
        self._asr = asr
        self._describer = image_describer
        self._extra_handlers: dict[ContentType, list[Callable]] = {}

    def register_handler(self, content_type: ContentType, handler) -> None:
        self._extra_handlers.setdefault(content_type, []).append(handler)

    async def understand(self, msg: SocialMessage, depth: int = 0, _ancestors: frozenset[int] | None = None) -> str:
        _ancestors = _ancestors or frozenset()
        identity = id(msg)
        if identity in _ancestors:
            return ""
        ancestors = _ancestors | {identity}
        parts: list[str] = []
        who = msg.sender_context()

        async def understand_images() -> list[str]:
            urls = msg.all_media_urls()

            async def describe(index: int, image_url: str) -> str:
                fallback = msg.media_descs[index] if index < len(msg.media_descs) else ""
                if not fallback and index == 0:
                    fallback = msg.media_desc
                if not self._describer:
                    return fallback or "图片内容暂时无法识别"
                try:
                    desc = await self._describer.describe(image_url)
                    return desc.description if desc else fallback or "图片内容暂时无法识别"
                except Exception:
                    return fallback or "图片内容暂时无法识别"

            details = await asyncio.gather(*(describe(index, url) for index, url in enumerate(urls)))
            if not details and msg.type == ContentType.IMAGE:
                details = [msg.media_desc or "图片内容暂时无法识别"]
            result: list[str] = []
            for index, detail in enumerate(details):
                label = f"图片{index + 1}/{len(details)}" if len(details) > 1 else "图片"
                result.append(f"{who}: [{label}] {detail}")
            return result

        for handler in self._extra_handlers.get(msg.type, []):
            result = handler(msg)
            if hasattr(result, "__await__"):
                result = await result
            if result:
                parts.append(f"{who}: {result}")

        if msg.type == ContentType.TEXT:
            parts.append(f"{who}\n[用户文字] {msg.text}")
        elif msg.type == ContentType.VOICE:
            text = await self._asr.transcribe(msg.media_url) if self._asr else ""
            parts.append(f"{who}: [语音] {text or msg.media_desc or '(无法识别)'}")
        elif msg.type == ContentType.IMAGE:
            parts.extend(await understand_images())
            if msg.text:
                parts.append(f"{who}: [图片附言] {msg.text}")
        elif msg.type == ContentType.STICKER:
            parts.append(f"{who}: [表情] {msg.text}")
        elif msg.type == ContentType.FORWARD:
            parts.append(f"{who}: [转发的聊天记录]")
            if msg.text:
                parts.append(f"  附言：{msg.text}")
            sub_texts = await asyncio.gather(
                *(self.understand(sub, depth + 1, ancestors) for sub in msg.sub_messages)
            )
            for sub_text in sub_texts:
                if sub_text:
                    parts.append("  " + sub_text)
            if not msg.sub_messages:
                parts.append("  （聊天记录内容获取失败）")
        elif msg.type == ContentType.QUOTE:
            quote_text = await self.understand(msg.quote_ref, depth + 1, ancestors) if msg.quote_ref else ""
            parts.append(f"{who}: 引用「{quote_text.strip()}」回复: {msg.text}")
        elif msg.type == ContentType.FILE:
            parts.append(f"{who}: [文件] {msg.text or msg.media_url}")

        if msg.type != ContentType.IMAGE and msg.all_media_urls():
            parts.extend(await understand_images())

        return "\n".join(p for p in parts if p)


def create_asr(kind: str, **opts) -> ASREngine:
    cls = asr_registry.get(kind)
    return cls(**opts)  # type: ignore
