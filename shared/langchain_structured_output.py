from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from shared.mcp_output_client import MCPOutputClient
from shared.structured_output_tools import output_tool

OutputT = TypeVar("OutputT", bound=BaseModel)


def structured_output_runnable(
    model: BaseChatModel,
    output_type: type[OutputT],
    max_attempts: int,
    output_client: MCPOutputClient,
) -> Runnable:
    spec = output_tool(output_type)
    bound_model = model.bind_tools([spec.model_tool()], tool_choice=spec.name)

    async def invoke(messages, config):
        raw = await bound_model.ainvoke(messages, config=config)
        if not isinstance(raw, AIMessage) or raw.invalid_tool_calls or len(raw.tool_calls) != 1:
            raise ValueError(f"结果需要一次 {spec.name} 工具调用")
        call = raw.tool_calls[0]
        if call["name"] != spec.name:
            raise ValueError(f"结果工具应为 {spec.name}")
        output = await output_client.submit(output_type, call["args"])
        return {"raw": raw, "parsed": output}

    runnable = RunnableLambda(invoke)
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
