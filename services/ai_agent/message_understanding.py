
from __future__ import annotations

import asyncio
import json

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

    def __init__(self, prompts, fallbacks: dict, asr: ASREngine | None = None, image_describer=None) -> None:
        self._prompts = prompts
        self._fallbacks = fallbacks
        self._asr = asr
        self._describer = image_describer
        self._extra_handlers: dict[ContentType, list[Callable]] = {}

    def register_handler(self, content_type: ContentType, handler) -> None:
        self._extra_handlers.setdefault(content_type, []).append(handler)

    async def understand(self, msg: SocialMessage, _ancestors: frozenset[int] | None = None) -> str:
        _ancestors = _ancestors or frozenset()
        identity = id(msg)
        if identity in _ancestors:
            return ""
        ancestors = _ancestors | {identity}
        parts: list[str] = []
        who = self._prompts.render(
            "message-sender",
            user_id=json.dumps(str(msg.sender.user_id), ensure_ascii=False),
            nickname=json.dumps(str(msg.sender.name or ""), ensure_ascii=False),
        )

        async def understand_images() -> list[str]:
            urls = msg.all_media_urls()

            async def describe(index: int, image_url: str) -> str:
                fallback = msg.media_descs[index] if index < len(msg.media_descs) else ""
                if not fallback and index == 0:
                    fallback = msg.media_desc
                if not self._describer:
                    return fallback or self._fallbacks["image_unreadable"]
                try:
                    desc = await self._describer.describe(image_url)
                    return desc.description if desc else fallback or self._fallbacks["image_unreadable"]
                except Exception:
                    return fallback or self._fallbacks["image_unreadable"]

            details = await asyncio.gather(*(describe(index, url) for index, url in enumerate(urls)))
            if not details and msg.type == ContentType.IMAGE:
                details = [msg.media_desc or self._fallbacks["image_unreadable"]]
            result: list[str] = []
            for index, detail in enumerate(details):
                label = (
                    self._prompts.render(
                        "message-image-label-multiple",
                        index=index + 1,
                        total=len(details),
                    )
                    if len(details) > 1
                    else self._prompts.template("message-image-label-single")
                )
                result.append(self._prompts.render("message-media", who=who, label=label, detail=detail))
            return result

        for handler in self._extra_handlers.get(msg.type, []):
            result = handler(msg)
            if hasattr(result, "__await__"):
                result = await result
            if result:
                parts.append(self._prompts.render("message-extra", who=who, result=result))

        if msg.type == ContentType.TEXT:
            parts.append(self._prompts.render("message-text", who=who, text=msg.text))
        elif msg.type == ContentType.VOICE:
            text = await self._asr.transcribe(msg.media_url) if self._asr else ""
            parts.append(self._prompts.render(
                "message-voice",
                who=who,
                text=text or msg.media_desc or self._fallbacks["voice_unrecognized"],
            ))
        elif msg.type == ContentType.IMAGE:
            parts.extend(await understand_images())
            if msg.text:
                parts.append(self._prompts.render("message-image-caption", who=who, text=msg.text))
        elif msg.type == ContentType.STICKER:
            parts.append(self._prompts.render("message-sticker", who=who, text=msg.text))
        elif msg.type == ContentType.FORWARD:
            parts.append(self._prompts.render("message-forward", who=who))
            if msg.text:
                parts.append(self._prompts.render("message-forward-caption", text=msg.text))
            sub_texts = await asyncio.gather(
                *(self.understand(sub, ancestors) for sub in msg.sub_messages)
            )
            for sub_text in sub_texts:
                if sub_text:
                    parts.append(self._prompts.render("message-nested", text=sub_text))
            if not msg.sub_messages:
                parts.append(self._prompts.template("message-forward-unavailable"))
        elif msg.type == ContentType.QUOTE:
            quote_text = await self.understand(msg.quote_ref, ancestors) if msg.quote_ref else ""
            parts.append(self._prompts.render(
                "message-quote", who=who, quote=quote_text.strip(), text=msg.text
            ))
        elif msg.type == ContentType.FILE:
            parts.append(self._prompts.render(
                "message-file", who=who, text=msg.text or msg.media_url
            ))

        if msg.type != ContentType.IMAGE and msg.all_media_urls():
            parts.extend(await understand_images())

        return self._prompts.template("message-separator").join(p for p in parts if p)


def create_asr(kind: str, **opts) -> ASREngine:
    cls = asr_registry.get(kind)
    return cls(**opts)
