from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from agentscope.message import Msg
from opentelemetry import trace
from opentelemetry.trace import Span
from pydantic import BaseModel

from shared.global_settings import ObservabilitySettings

tracer = trace.get_tracer("ai-love.agentscope")


def model_span(
    operation: str,
    model: str,
    settings: ObservabilitySettings,
    request_parameters: Mapping[str, str | int | float] | None = None,
):
    provider, separator, model_name = model.partition(":")
    attributes: dict[str, str | int | float] = {
        "gen_ai.request.model": model_name if separator else model,
    }
    if separator:
        attributes["gen_ai.provider.name"] = provider
    if settings.include_model_request_parameters and request_parameters:
        for name, value in request_parameters.items():
            attributes[f"gen_ai.request.{name}"] = value
    return tracer.start_as_current_span(
        operation,
        attributes=attributes,
    )


def tool_span(tool_name: str):
    return tracer.start_as_current_span(
        "tool.execute",
        attributes={"gen_ai.tool.name": tool_name},
    )


def record_messages_usage(span: Span, messages: Iterable[Any]) -> None:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    has_usage = False
    for message in messages:
        if not isinstance(message, Msg) or not message.usage:
            continue
        has_usage = True
        input_tokens += int(message.usage.input_tokens)
        output_tokens += int(message.usage.output_tokens)
        total_tokens += int(message.usage.input_tokens + message.usage.output_tokens)
    if has_usage:
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        span.set_attribute("gen_ai.usage.total_tokens", total_tokens)


def record_model_content(
    span: Span,
    settings: ObservabilitySettings,
    *,
    input_text: str,
    output: BaseModel,
) -> None:
    if settings.include_model_content:
        span.set_attribute("gen_ai.input", input_text)
        span.set_attribute("gen_ai.output", output.model_dump_json())
