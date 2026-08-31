from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agent.conversation.message_understanding import MessageUnderstanding
from agent.vision.image_fetcher import ImageFetcher
from shared.contracts.social import ContentType, SocialMessage


@dataclass(frozen=True)
class ImageAttachment:
    source_url: str
    data_url: str
    attribution: str


@dataclass(frozen=True)
class MessageInput:
    text: str
    images: tuple[ImageAttachment, ...] = ()


class DescribedMessageInputBuilder:
    def __init__(self, understanding: MessageUnderstanding) -> None:
        self._understanding = understanding

    async def build(self, msg: SocialMessage) -> MessageInput:
        return MessageInput(text=await self._understanding.understand(msg))


class DirectVisionMessageInputBuilder:
    def __init__(
        self,
        prompts,
        handlers: Mapping[ContentType, tuple[Callable, ...]],
        image_fetcher: ImageFetcher,
    ) -> None:
        self._prompts = prompts
        self._handlers = handlers
        self._image_fetcher = image_fetcher

    async def build(self, msg: SocialMessage) -> MessageInput:
        understood = await self._understand(msg)
        data_urls = await self._image_fetcher.data_urls([image.source_url for image in understood.images])
        images = tuple(
            ImageAttachment(
                source_url=image.source_url,
                data_url=data_url,
                attribution=image.attribution,
            )
            for image, data_url in zip(understood.images, data_urls, strict=True)
        )
        return MessageInput(text=understood.text, images=images)

    async def _understand(
        self,
        msg: SocialMessage,
        ancestors: frozenset[int] | None = None,
    ) -> MessageInput:
        ancestors = ancestors or frozenset()
        identity = id(msg)
        if identity in ancestors:
            raise ValueError("消息引用结构存在循环")
        ancestors |= {identity}
        parts: list[str] = []
        images: list[ImageAttachment] = []
        who = self._prompts.render(
            "message-sender",
            name=str(msg.sender.name or msg.sender.user_id),
        )

        def understand_images() -> tuple[list[str], list[ImageAttachment]]:
            urls = msg.all_media_urls()
            if not urls and msg.type == ContentType.IMAGE:
                if not msg.media_desc:
                    raise ValueError("图片消息缺少图片地址和描述")
                text = self._prompts.render("message-media", who=who, label="图片", detail=msg.media_desc)
                return [text], []

            image_parts: list[str] = []
            attachments: list[ImageAttachment] = []
            for index, url in enumerate(urls):
                label = (
                    self._prompts.render(
                        "message-image-label-multiple",
                        index=index + 1,
                        total=len(urls),
                    )
                    if len(urls) > 1
                    else self._prompts.template("message-image-label-single")
                )
                detail = ""
                if index < len(msg.media_descs) and msg.media_descs[index]:
                    detail = msg.media_descs[index]
                elif index == 0 and msg.media_desc:
                    detail = msg.media_desc
                attribution = self._prompts.render(
                    "message-media",
                    who=who,
                    label=label,
                    detail=detail,
                ).rstrip()
                image_parts.append(attribution)
                attachments.append(
                    ImageAttachment(
                        source_url=url,
                        data_url="",
                        attribution=attribution,
                    )
                )
            return image_parts, attachments

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
            parts.append(self._prompts.render("message-voice", who=who, text=msg.media_desc))
        elif msg.type == ContentType.IMAGE:
            image_parts, attachments = understand_images()
            parts.extend(image_parts)
            images.extend(attachments)
            if msg.text:
                parts.append(self._prompts.render("message-image-caption", who=who, text=msg.text))
        elif msg.type == ContentType.STICKER:
            parts.append(self._prompts.render("message-sticker", who=who, text=msg.text))
        elif msg.type == ContentType.FORWARD:
            parts.append(self._prompts.render("message-forward", who=who))
            if msg.text:
                parts.append(self._prompts.render("message-forward-caption", text=msg.text))
            sub_inputs = await asyncio.gather(*(self._understand(sub, ancestors) for sub in msg.sub_messages))
            for sub_input in sub_inputs:
                if sub_input.text:
                    parts.append(self._prompts.render("message-nested", text=sub_input.text))
                images.extend(sub_input.images)
            if not msg.sub_messages:
                parts.append(self._prompts.template("message-forward-unavailable"))
        elif msg.type == ContentType.QUOTE:
            quote_input = await self._understand(msg.quote_ref, ancestors) if msg.quote_ref else MessageInput("")
            parts.append(self._prompts.render("message-quote", who=who, quote=quote_input.text.strip(), text=msg.text))
            images.extend(quote_input.images)
        elif msg.type == ContentType.FILE:
            parts.append(self._prompts.render("message-file", who=who, text=msg.text or msg.media_url))

        if msg.type != ContentType.IMAGE and msg.all_media_urls():
            image_parts, attachments = understand_images()
            parts.extend(image_parts)
            images.extend(attachments)

        text = self._prompts.template("message-separator").join(part for part in parts if part)
        return MessageInput(text=text, images=tuple(images))
