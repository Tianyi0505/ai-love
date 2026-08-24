from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)


def structured_output_runnable(
    model: BaseChatModel,
    output_type: type[OutputT],
    max_attempts: int,
) -> Runnable:
    def require_parsed(result: object) -> object:
        parsed_output(result, output_type)
        return result

    runnable = model.with_structured_output(
        output_type,
        include_raw=True,
    ) | RunnableLambda(require_parsed)
    if max_attempts > 1:
        return runnable.with_retry(
            stop_after_attempt=max_attempts,
            wait_exponential_jitter=False,
        )
    return runnable


def parsed_output(result: object, output_type: type[OutputT]) -> OutputT:
    if not isinstance(result, dict):
        raise RuntimeError(f"模型未返回 {output_type.__name__}")
    parsed = result.get("parsed")
    if isinstance(parsed, output_type):
        return parsed
    error = result.get("parsing_error")
    if isinstance(error, BaseException):
        raise error
    raise RuntimeError(f"模型未返回 {output_type.__name__}")
