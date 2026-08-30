from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

from shared.contracts.social import ContentType, SocialMessage


# 描述消息理解结果
class MessageUnderstanding:
    # 初始化当前实例
    def __init__(
        self,
        prompts,
        handlers: Mapping[ContentType, tuple[Callable, ...]],
        image_describer,
    ) -> None:
        self._prompts = prompts
        self._handlers = handlers
        self._describer = image_describer

    # 理解社交消息
    async def understand(self, msg: SocialMessage, _ancestors: frozenset[int] | None = None) -> str:
        if _ancestors is None:
            _ancestors = frozenset()
        identity = id(msg)
        if identity in _ancestors:
            raise ValueError("消息引用结构存在循环")
        ancestors = _ancestors | {identity}
        parts: list[str] = []
        who = self._prompts.render(
            "message-sender",
            name=str(msg.sender.name or msg.sender.user_id),
        )

        # 理解消息中的图片
        async def understand_images() -> list[str]:
            urls = msg.all_media_urls()

            # 描述图片内容
            async def describe(index: int, image_url: str) -> str:
                if index < len(msg.media_descs) and msg.media_descs[index]:
                    return msg.media_descs[index]
                if index == 0 and msg.media_desc:
                    return msg.media_desc
                return (await self._describer.describe(image_url)).description

            details = await asyncio.gather(*(describe(index, url) for index, url in enumerate(urls)))
            if not details and msg.type == ContentType.IMAGE:
                if not msg.media_desc:
                    raise ValueError("图片消息缺少图片地址和描述")
                details = [msg.media_desc]
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

        for handler in self._handlers.get(msg.type, ()):
            result = handler(msg)
            if hasattr(result, "__await__"):
                result = await result
            if result:
                parts.append(self._prompts.render("message-extra", who=who, result=result))

        if msg.type == ContentType.TEXT:
            parts.append(self._prompts.render("message-text", who=who, text=msg.text))
        elif msg.type == ContentType.VOICE:
            if not msg.media_desc:
                raise ValueError("当前未配置语音识别能力")
            parts.append(
                self._prompts.render(
                    "message-voice",
                    who=who,
                    text=msg.media_desc,
                )
            )
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
            sub_texts = await asyncio.gather(*(self.understand(sub, ancestors) for sub in msg.sub_messages))
            for sub_text in sub_texts:
                if sub_text:
                    parts.append(self._prompts.render("message-nested", text=sub_text))
            if not msg.sub_messages:
                parts.append(self._prompts.template("message-forward-unavailable"))
        elif msg.type == ContentType.QUOTE:
            quote_text = await self.understand(msg.quote_ref, ancestors) if msg.quote_ref else ""
            parts.append(self._prompts.render("message-quote", who=who, quote=quote_text.strip(), text=msg.text))
        elif msg.type == ContentType.FILE:
            parts.append(self._prompts.render("message-file", who=who, text=msg.text or msg.media_url))

        if msg.type != ContentType.IMAGE and msg.all_media_urls():
            parts.extend(await understand_images())

        return self._prompts.template("message-separator").join(p for p in parts if p)
