
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from ai.llm.service import LLMService
from ai.llm.types import ChatMessage, ChatRequest, ChatStreamChunk, ToolSchema

logger = logging.getLogger("ailove.agent_loop")


# 执行智能体工具调用循环
class AgentLoop:

    # 初始化当前实例
    def __init__(self, llm: LLMService, prompts, ai_id: str, max_rounds: int) -> None:
        self._llm = llm
        self._prompts = prompts
        self._ai_id = ai_id
        self._max_rounds = max_rounds
        self._tools: dict[str, Callable[[dict], Awaitable[str]]] = {}

    # 注册工具
    def register_tool(self, name: str, tool_info: dict, executor) -> None:
        self._tools[name] = executor
        self._tool_infos = getattr(self, "_tool_infos", {})
        self._tool_infos[name] = tool_info

    # 运行主流程
    async def run(self, messages: list[ChatMessage]) -> str:
        tool_schemas = [ToolSchema(name=n, description=i.get("description", ""), parameters=i.get("parameters", {})) for n, i in getattr(self, "_tool_infos", {}).items()]
        if tool_schemas:
            prompt = self._prompts.render(
                "tool-usage",
                tools="\n".join(f"- {s.name}: {s.description}" for s in tool_schemas)
            )
            if messages and messages[0].role == "system":
                messages = [ChatMessage(role="system", content=f"{messages[0].content}\n\n{prompt}")] + messages[1:]
            else:
                messages = [ChatMessage(role="system", content=prompt)] + messages

        current = list(messages)
        for _ in range(self._max_rounds):
            parts: list[str] = []
            tool_calls = []
            async for chunk in self._llm.chat(ChatRequest(ai_id=self._ai_id, messages=current, tools=tool_schemas)):
                if chunk.content:
                    parts.append(chunk.content)
                if chunk.tool_call:
                    tool_calls.append(chunk.tool_call)
            text = "".join(parts).strip()

            if not tool_calls:
                return text

            for tc in tool_calls:
                executor = self._tools.get(tc.name)
                if executor is None:
                    result = f"未知工具: {tc.name}"
                else:
                    try:
                        result = await executor(tc.arguments or {})
                    except Exception as e:
                        result = f"工具执行失败: {e}"
                logger.info("[agent_loop] 调用工具 %s: %s", tc.name, str(result)[:50])
                current.append(ChatMessage(role="assistant", content=text))
                current.append(ChatMessage(
                    role="user",
                    content=self._prompts.render("tool-result", tool_name=tc.name, result=result),
                ))

        return "".join(parts).strip()
