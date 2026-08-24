from __future__ import annotations

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ai.vision.image_description import ImageDescription
from ai.vision.image_fetcher import ImageFetcher
from ai.vision.vision_output_policy import VisionOutputPolicy
from shared.configuration.global_settings import ObservabilitySettings


class ImageDescriber:
    def __init__(
        self,
        model: Model,
        fetcher: ImageFetcher,
        output_policy: VisionOutputPolicy,
        prompt: str,
        max_tokens: int,
        retry_count: int,
        observability: ObservabilitySettings,
    ) -> None:
        self._fetcher = fetcher
        self._output_policy = output_policy
        self._prompt = prompt
        self._agent = Agent(
            model=model,
            output_type=ImageDescription,
            model_settings=ModelSettings(max_tokens=max_tokens),
            retries=retry_count,
        )
        self._agent.instrument = InstrumentationSettings(
            include_content=observability.include_model_content,
            include_binary_content=observability.include_binary_content,
            include_model_request_parameters=observability.include_model_request_parameters,
        )

    async def describe(self, image_url: str) -> ImageDescription:
        image = await self._fetcher.fetch(image_url)
        result = await self._agent.run([self._prompt, image])
        return self._output_policy.validate(result.output)
