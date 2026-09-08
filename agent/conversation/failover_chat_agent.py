from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.response_plan import ParticipationDecision, ResponsePlan
from agent.vision.image_describer import ImageDescriber
from shared.contracts.tools import ToolExecutionContext

logger = logging.getLogger("ailove.ai-agent.model-failover")


class FailoverChatAgent:
    def __init__(
        self,
        primaries: Sequence[tuple[str, ChatAgent]],
        fallback: ChatAgent,
        image_describer: ImageDescriber,
        fallback_model_name: str,
    ) -> None:
        self._primaries = tuple(primaries)
        self._fallback = fallback
        self._image_describer = image_describer
        self._fallback_model_name = fallback_model_name

    async def generate_plan(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_context: ToolExecutionContext | None = None,
        allow_tools: bool = True,
        images: Sequence[ImageAttachment] = (),
    ) -> ResponsePlan:
        for model_name, primary in self._primaries:
            try:
                return await primary.generate_plan(
                    system_prompt,
                    user_prompt,
                    tool_context=tool_context,
                    allow_tools=allow_tools,
                    images=images,
                )
            except Exception as exc:
                self._log_primary_failure(model_name, exc)
        self._log_fallback()
        return await self._fallback.generate_plan(
            system_prompt,
            await self._fallback_prompt(user_prompt, images),
            tool_context=tool_context,
            allow_tools=allow_tools,
        )

    async def decide_participation(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Sequence[ImageAttachment] = (),
    ) -> ParticipationDecision:
        for model_name, primary in self._primaries:
            try:
                return await primary.decide_participation(
                    system_prompt,
                    user_prompt,
                    images=images,
                )
            except Exception as exc:
                self._log_primary_failure(model_name, exc)
        self._log_fallback()
        return await self._fallback.decide_participation(
            system_prompt,
            await self._fallback_prompt(user_prompt, images),
        )

    async def _fallback_prompt(
        self,
        user_prompt: str,
        images: Sequence[ImageAttachment],
    ) -> str:
        if not images:
            return user_prompt
        descriptions = await asyncio.gather(
            *(self._image_describer.describe(image.source_url) for image in images)
        )
        if images[0].is_group:
            prompt = json.loads(user_prompt)
            records = []
            for image, description in zip(images, descriptions, strict=True):
                record = json.loads(image.attribution)
                record["用户发的消息/图片"] = {
                    "图片": record["用户发的消息/图片"],
                    "识别结果": description.description,
                }
                records.append(record)
            prompt["图片识别结果"] = records
            return json.dumps(prompt, ensure_ascii=False)
        image_text = "\n".join(
            f"{image.attribution} {description.description}"
            for image, description in zip(images, descriptions, strict=True)
        )
        return f"{user_prompt}\n\n以下是图片识别结果，已按原消息发送者对应：\n{image_text}"

    @staticmethod
    def _log_primary_failure(model_name: str, error: Exception) -> None:
        logger.warning(
            "多模态模型 %s 调用失败，继续尝试同组下一模型: %s",
            model_name,
            error,
        )

    def _log_fallback(self) -> None:
        logger.warning(
            "多模态模型组全部不可用，降级到独立视觉模型 + 文本模型 %s",
            self._fallback_model_name,
        )
