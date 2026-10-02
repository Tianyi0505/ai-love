from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agentscope.credential import AnthropicCredential, DeepSeekCredential, OpenAICredential
from agentscope.model import AnthropicChatModel, ChatModelBase, DeepSeekChatModel, OpenAIChatModel

AGNES_FREE_CHAT_MODELS = frozenset({"agnes-2.5-flash", "agnes-3.0-flash"})


@dataclass(frozen=True, slots=True)
class ChatModelParameters:
    model: str
    api_key: str = field(repr=False)
    base_url: str
    max_tokens: int
    timeout_sec: float
    max_retries: int


class ChatModelStrategy(ABC):
    @abstractmethod
    def create(self, parameters: ChatModelParameters) -> ChatModelBase: ...


class DeepSeekChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> ChatModelBase:
        return DeepSeekChatModel(
            credential=DeepSeekCredential(api_key=parameters.api_key, base_url=parameters.base_url),
            model=parameters.model,
            parameters=DeepSeekChatModel.Parameters(max_tokens=parameters.max_tokens, thinking_enable=False),
            stream=False,
            max_retries=parameters.max_retries,
            client_kwargs={"timeout": parameters.timeout_sec, "max_retries": 0},
        )


class AnthropicChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> ChatModelBase:
        return AnthropicChatModel(
            credential=AnthropicCredential(api_key=parameters.api_key, base_url=parameters.base_url),
            model=parameters.model,
            parameters=AnthropicChatModel.Parameters(max_tokens=parameters.max_tokens),
            stream=False,
            max_retries=parameters.max_retries,
            client_kwargs={"timeout": parameters.timeout_sec, "max_retries": 0},
        )


class OpenAIChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> ChatModelBase:
        return OpenAIChatModel(
            credential=OpenAICredential(api_key=parameters.api_key, base_url=parameters.base_url),
            model=parameters.model,
            parameters=OpenAIChatModel.Parameters(max_tokens=parameters.max_tokens),
            stream=False,
            max_retries=parameters.max_retries,
            client_kwargs={"timeout": parameters.timeout_sec, "max_retries": 0},
        )


class AgnesChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> ChatModelBase:
        if parameters.model not in AGNES_FREE_CHAT_MODELS:
            raise ValueError(f"Agnes 仅接入已核对免费的对话模型: {parameters.model}")
        return OpenAIChatModel(
            credential=OpenAICredential(api_key=parameters.api_key, base_url=parameters.base_url),
            model=parameters.model,
            extra_body={"max_tokens": parameters.max_tokens},
            stream=False,
            max_retries=parameters.max_retries,
            client_kwargs={"timeout": parameters.timeout_sec, "max_retries": 0},
        )


CHAT_MODEL_STRATEGIES: dict[str, ChatModelStrategy] = {
    "deepseek": DeepSeekChatModelStrategy(),
    "anthropic": AnthropicChatModelStrategy(),
    "openai": OpenAIChatModelStrategy(),
    "agnes": AgnesChatModelStrategy(),
}
