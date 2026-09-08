from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from agent.conversation.conversation_context import group_message_record
from agent.conversation.multimodal_input import ImageAttachment, MessageInput
from shared.contracts.social import ChatType, ContentType, SocialMessage


class SocialMessageInputBuilder:
    """按会话场景构建模型消息并将群聊内容序列化为 JSON"""

    def __init__(self, private_builder, conversation, image_fetcher, image_describer, *, direct_vision: bool) -> None:
        self._private_builder = private_builder
        self._conversation = conversation
        self._image_fetcher = image_fetcher
        self._image_describer = image_describer
        self._direct_vision = direct_vision

    async def build(self, msg: SocialMessage) -> MessageInput:
        if msg.chat.chat_type != ChatType.GROUP:
            return await self._private_builder.build(msg)
        record, images = await self._group_message(msg, frozenset())
        if images:
            data_urls = await self._image_fetcher.data_urls([image.source_url for image in images])
            images = [replace(image, data_url=url) for image, url in zip(images, data_urls, strict=True)]
        return MessageInput(json.dumps(record, ensure_ascii=False), tuple(images), record)

    async def _group_message(self, msg: SocialMessage, ancestors: frozenset[int]) -> tuple[dict, list[ImageAttachment]]:
        if id(msg) in ancestors:
            raise ValueError("消息引用结构存在循环")
        ancestors = ancestors | {id(msg)}
        timestamp = self._conversation.format_timestamp(msg.timestamp)
        name = msg.sender.name or msg.sender.user_id
        content: list[dict] = []
        images: list[ImageAttachment] = []
        if msg.text:
            content.append({"类型": "sticker" if msg.type == ContentType.STICKER else "text", "文字": msg.text})
        if msg.meta.get("at_user_ids"):
            content.append({"类型": "at", "用户": msg.meta["at_user_ids"]})
        if msg.type == ContentType.VOICE:
            if not msg.media_desc:
                raise ValueError("当前未配置语音识别能力")
            content.append({"类型": "voice", "文字": msg.media_desc})
        elif msg.type == ContentType.FILE:
            content.append({"类型": "file", "名称": msg.text, "地址": msg.media_url})

        urls = msg.media_urls or (
            [msg.media_url] if msg.type in {ContentType.IMAGE, ContentType.STICKER} and msg.media_url else []
        )
        for index, url in enumerate(urls):
            description = msg.media_descs[index] if index < len(msg.media_descs) else ""
            if index == 0 and not description:
                description = msg.media_desc
            if not self._direct_vision and not description:
                description = (await self._image_describer.describe(url)).description
            picture = {"类型": "image", "图片序号": index + 1, "地址": url, "描述": description}
            content.append(picture)
            if self._direct_vision:
                attribution = group_message_record(timestamp, name, [picture])
                images.append(ImageAttachment(url, "", json.dumps(attribution, ensure_ascii=False), is_group=True))
        if msg.type == ContentType.IMAGE and not urls:
            if not msg.media_desc:
                raise ValueError("图片消息缺少图片地址和描述")
            content.append({"类型": "image", "描述": msg.media_desc})

        if msg.quote_ref is not None:
            quote, quote_images = await self._group_message(msg.quote_ref, ancestors)
            content.append({"类型": "quote", "消息": quote})
            images.extend(quote_images)
        if msg.type == ContentType.FORWARD:
            children = await asyncio.gather(*(self._group_message(child, ancestors) for child in msg.sub_messages))
            content.append({"类型": "forward", "消息": [record for record, _ in children]})
            for _, child_images in children:
                images.extend(child_images)
        return group_message_record(timestamp, name, content), images
