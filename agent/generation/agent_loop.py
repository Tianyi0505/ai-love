
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from ai.llm.service import LLMService
from ai.llm.types import ChatMessage, ChatRequest, ToolSchema
from shared.contracts.tools import ToolExecutionContext

logger = logging.getLogger("ailove.agent_loop")


# 执行智能体工具调用循环
class AgentLoop:

    # 初始化当前实例
    def __init__(self, llm: LLMService, prompts, ai_id: str, max_rounds: int) -> None:
        self._llm = llm
        self._prompts = prompts
        self._ai_id = ai_id
        self._max_rounds = max_rounds
        self._tools: dict[
            str,
            Callable[[dict, ToolExecutionContext], Awaitable[str]],
        ] = {}

    # 注册工具
    def register_tool(self, name: str, tool_info: dict, executor) -> None:
        self._tools[name] = executor
        self._tool_infos = getattr(self, "_tool_infos", {})
        self._tool_infos[name] = tool_info

    # 运行主流程
    async def run(
        self,
        messages: list[ChatMessage],
        *,
        tool_context: ToolExecutionContext | None = None,
        allow_tools: bool = True,
        on_step: Callable[[int, str, dict], Awaitable[None]] | None = None,
    ) -> str:
        tool_context = tool_context or ToolExecutionContext(ai_id=self._ai_id)
        tool_schemas = [ToolSchema(name=n, description=i.get("description", ""), parameters=i.get("parameters", {})) for n, i in getattr(self, "_tool_infos", {}).items()]
        if not allow_tools:
            tool_schemas = []
        if tool_schemas:
            context_lines: list[str] = []
            external_lines: list[str] = []
            for name, info in getattr(self, "_tool_infos", {}).items():
                line = f"- {name}: {info.get('description', '')}"
                if info.get("provider") == "grounding":
                    context_lines.append(line)
                else:
                    external_lines.append(line)
            prompt = self._prompts.render(
                "tool-usage",
                context_tools="\n".join(context_lines),
                external_tools="\n".join(external_lines),
            )
            if messages and messages[0].role == "system":
                messages = [ChatMessage(role="system", content=f"{messages[0].content}\n\n{prompt}")] + messages[1:]
            else:
                messages = [ChatMessage(role="system", content=prompt)] + messages

        current = list(messages)
        step_index = 0
        for _ in range(self._max_rounds):
            parts: list[str] = []
            tool_calls = []
            async for chunk in self._llm.chat(ChatRequest(ai_id=self._ai_id, messages=current, tools=tool_schemas)):
                if chunk.content:
                    parts.append(chunk.content)
                if chunk.tool_call:
                    tool_calls.append(chunk.tool_call)
            text = "".join(parts).strip()

            if not tool_calls or not allow_tools:
                await self._emit_step(on_step, step_index, "final", {"text": text})
                return text

            current.append(ChatMessage(role="assistant", content=text))
            for tc in tool_calls:
                executor = self._tools.get(tc.name)
                started = time.monotonic()
                if executor is None:
                    result = f"未知工具: {tc.name}"
                else:
                    try:
                        result = await executor(tc.arguments or {}, tool_context)
                    except Exception as e:
                        result = f"工具执行失败: {e}"
                logger.info("[agent_loop] 调用工具 %s: %s", tc.name, str(result)[:50])
                await self._emit_step(
                    on_step,
                    step_index,
                    "tool",
                    {
                        "tool_name": tc.name,
                        "arguments": tc.arguments or {},
                        "result": str(result)[:2000],
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                step_index += 1
                current.append(ChatMessage(
                    role="user",
                    content=self._prompts.render("tool-result", tool_name=tc.name, result=result),
                ))

        # 工具阶段结束后再给一次纯生成机会
        parts = []
        async for chunk in self._llm.chat(
            ChatRequest(ai_id=self._ai_id, messages=current, tools=[])
        ):
            if chunk.content:
                parts.append(chunk.content)
        text = "".join(parts).strip()
        await self._emit_step(on_step, step_index, "final", {"text": text})
        return text

    # 上报执行步骤，不干扰主流程
    @staticmethod
    async def _emit_step(on_step, index: int, kind: str, data: dict) -> None:
        if on_step is None:
            return
        try:
            await on_step(index, kind, data)
        except Exception:
            logger.exception("[agent_loop] 执行步骤上报失败")
