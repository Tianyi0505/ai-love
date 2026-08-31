from __future__ import annotations

import re
from string import Template

from agent.conversation.failover_chat_agent import FailoverChatAgent
from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.prompt_assembler import PromptAssembler, PromptContext
from agent.vision.image_fetcher import ImageFetcher
from shared.contracts.rpc.social import CommentRequest, CommentResponse
from shared.global_settings import QQSettings


class DirectVisionQZoneCommentGenerator:
    def __init__(
        self,
        settings: QQSettings,
        prompt_assembler: PromptAssembler,
        chat_agent: FailoverChatAgent,
        image_fetcher: ImageFetcher,
    ) -> None:
        self._settings = settings
        self._prompt_assembler = prompt_assembler
        self._chat_agent = chat_agent
        self._image_fetcher = image_fetcher

    async def generate(self, request: CommentRequest) -> CommentResponse:
        feed_text = request.feed_text
        images: tuple[ImageAttachment, ...] = ()
        if request.picture_urls:
            data_urls = await self._image_fetcher.data_urls(request.picture_urls)
            total = len(data_urls)
            images = tuple(
                ImageAttachment(
                    source_url=source_url,
                    data_url=data_url,
                    attribution=f"{request.author_name}: [动态图片{index}/{total}]",
                )
                for index, (source_url, data_url) in enumerate(
                    zip(request.picture_urls, data_urls, strict=True),
                    start=1,
                )
            )
            picture_text = "\n".join(
                Template(self._settings.qzone_picture_template).substitute(
                    index=index,
                    description="内容见随附图片",
                )
                for index in range(1, total + 1)
            )
            feed_text = (
                Template(self._settings.qzone_feed_template)
                .substitute(
                    content=feed_text,
                    pictures=picture_text,
                    comments="",
                    reply="",
                )
                .strip()
            )
        context = PromptContext(
            scene="qzone-comment",
            user_input=self._prompt_assembler.render(
                "qzone-comment-input",
                author_name=request.author_name,
                feed_text=feed_text,
            ),
            relationship_summary=self._prompt_assembler.render(
                "qzone-comment-relationship",
                author_name=request.author_name,
            ),
        )
        plan = await self._chat_agent.generate_plan(
            self._prompt_assembler.build_system_prompt(context),
            self._prompt_assembler.build_user_prompt(context),
            images=images,
        )
        sentences = re.split(r"(?<=[。！？!?])", plan.text.strip())
        comment = "".join(sentences[: self._settings.qzone_comment_max_sentences])
        return CommentResponse(comment=comment)
