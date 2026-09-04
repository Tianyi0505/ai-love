from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI


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
    def create(self, parameters: ChatModelParameters) -> BaseChatModel: ...


class DeepSeekChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> BaseChatModel:
        return ChatDeepSeek(
            model=parameters.model,
            api_key=parameters.api_key,
            base_url=parameters.base_url,
            extra_body={"thinking": {"type": "disabled"}},
            max_tokens=parameters.max_tokens,
            timeout=parameters.timeout_sec,
            max_retries=parameters.max_retries,
        )


class AnthropicChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> BaseChatModel:
        return ChatAnthropic(
            model=parameters.model,
            api_key=parameters.api_key,
            base_url=parameters.base_url,
            max_tokens=parameters.max_tokens,
            timeout=parameters.timeout_sec,
            max_retries=parameters.max_retries,
        )


class OpenAIChatModelStrategy(ChatModelStrategy):
    def create(self, parameters: ChatModelParameters) -> BaseChatModel:
        return ChatOpenAI(
            model=parameters.model,
            api_key=parameters.api_key,
            base_url=parameters.base_url,
            max_tokens=parameters.max_tokens,
            timeout=parameters.timeout_sec,
            max_retries=parameters.max_retries,
        )


CHAT_MODEL_STRATEGIES: dict[str, ChatModelStrategy] = {
    "deepseek": DeepSeekChatModelStrategy(),
    "anthropic": AnthropicChatModelStrategy(),
    "openai": OpenAIChatModelStrategy(),
}
