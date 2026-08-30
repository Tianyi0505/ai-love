from __future__ import annotations

import asyncio
import re
from string import Template

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.prompt_assembler import PromptAssembler, PromptContext
from agent.vision.image_describer import ImageDescriber
from shared.contracts.rpc.social import CommentRequest, CommentResponse
from shared.global_settings import QQSettings


class QZoneCommentGenerator:
    def __init__(
        self,
        settings: QQSettings,
        prompt_assembler: PromptAssembler,
        chat_agent: ChatAgent,
        vision: ImageDescriber,
    ) -> None:
        self._settings = settings
        self._prompt_assembler = prompt_assembler
        self._chat_agent = chat_agent
        self._vision = vision

    async def generate(self, request: CommentRequest) -> CommentResponse:
        feed_text = request.feed_text
        if request.picture_urls:
            descriptions = await asyncio.gather(*(self._describe_image(url) for url in request.picture_urls))
            picture_text = "\n".join(
                Template(self._settings.qzone_picture_template).substitute(
                    index=index,
                    description=description,
                )
                for index, description in enumerate(descriptions, start=1)
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
        )
        sentences = re.split(r"(?<=[。！？!?])", plan.text.strip())
        comment = "".join(sentences[: self._settings.qzone_comment_max_sentences])
        return CommentResponse(comment=comment)

    async def _describe_image(self, image_url: str) -> str:
        return (await self._vision.describe(image_url)).description
