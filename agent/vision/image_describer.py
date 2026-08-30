from __future__ import annotations

import base64

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from agent.vision.image_description import ImageDescription
from agent.vision.image_fetcher import ImageFetcher
from agent.vision.vision_output_policy import VisionOutputPolicy
from shared.global_settings import ObservabilitySettings
from shared.langchain_observability import (
    model_span,
    record_messages_usage,
    record_model_content,
)
from shared.langchain_structured_output import (
    parsed_output,
    structured_output_runnable,
)


class ImageDescriber:
    def __init__(
        self,
        model: BaseChatModel,
        model_name: str,
        fetcher: ImageFetcher,
        output_policy: VisionOutputPolicy,
        prompt: str,
        max_tokens: int,
        retry_count: int,
        observability: ObservabilitySettings,
    ) -> None:
        self._model_name = model_name
        self._fetcher = fetcher
        self._output_policy = output_policy
        self._prompt = prompt
        self._max_tokens = max_tokens
        self._observability = observability
        self._model = structured_output_runnable(
            model,
            ImageDescription,
            retry_count + 1,
        )

    async def describe(self, image_url: str) -> ImageDescription:
        image = await self._fetcher.fetch(image_url)
        data_url = (
            f"data:{image.media_type};base64,"
            f"{base64.b64encode(image.data).decode('ascii')}"
        )
        message = HumanMessage(
            content=[
                {"type": "text", "text": self._prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        )
        with model_span(
            "vision.describe",
            self._model_name,
            self._observability,
            {"max_tokens": self._max_tokens},
        ) as span:
            if self._observability.include_binary_content:
                span.set_attribute("gen_ai.input.image", data_url)
            result = await self._model.ainvoke([message])
            output = parsed_output(result, ImageDescription)
            record_messages_usage(span, [result["raw"]])
            record_model_content(
                span,
                self._observability,
                input_text=self._prompt,
                output=output,
            )
        return self._output_policy.validate(output)
