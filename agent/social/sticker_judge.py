from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from shared.contracts.vision_output import StickerDecision as StickerDecision
from shared.langchain_observability import model_span, record_messages_usage, record_model_content
from shared.langchain_structured_output import parsed_output, structured_output_runnable

logger = logging.getLogger("ailove.ai-agent.sticker-judge")


class StickerJudge:
    """结合候选图片和当前对话判断表情是否适合发送"""

    def __init__(self, model, model_name, fetcher, prompt, max_tokens, retry_count, observability, output_client) -> None:
        self._model = structured_output_runnable(model, StickerDecision, retry_count + 1, output_client)
        self._model_name = model_name
        self._fetcher = fetcher
        self._prompt = prompt
        self._max_tokens = max_tokens
        self._observability = observability

    async def should_send(self, image_url: str, context: dict) -> bool:
        try:
            data_urls = await self._fetcher.data_urls([image_url])
            context_json = json.dumps(context, ensure_ascii=False)
            messages = [
                SystemMessage(content=self._prompt),
                HumanMessage(content=[
                    {"type": "text", "text": context_json},
                    {"type": "image_url", "image_url": {"url": data_urls[0]}},
                ]),
            ]
            with model_span(
                "sticker.judge", self._model_name, self._observability, {"max_tokens": self._max_tokens},
            ) as span:
                result = await self._model.ainvoke(messages)
                decision = parsed_output(result, StickerDecision)
                record_messages_usage(span, [result["raw"]])
                record_model_content(
                    span, self._observability, input_text=context_json, output=decision,
                )
            approved = decision.image_type == "sticker" and decision.suitable
            logger.info("表情发送判断: type=%s suitable=%s", decision.image_type, approved)
            return approved
        except Exception:
            logger.exception("表情发送判断失败 本轮采用文字回复")
            return False
