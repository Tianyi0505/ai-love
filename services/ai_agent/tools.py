
from __future__ import annotations

import json
import logging

logger = logging.getLogger("ailove.ai-agent.tools")


async def register_tools(agent_loop, bus, ai_id: str) -> None:
    try:
        response = await bus.request_json("tool.list.request", {"ai_id": ai_id}, timeout=3.0)
    except Exception as exc:
        logger.warning("[ai-agent:%s] Extension Host 暂不可用: %s", ai_id, exc)
        return

    for info in response.get("tools", []):
        name = str(info.get("name", ""))
        if not name:
            continue

        async def execute(arguments, tool_id=name):
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            result = await bus.request_json(
                "tool.execute.request",
                {"ai_id": ai_id, "tool_id": tool_id, "arguments": arguments},
                timeout=30.0,
            )
            return result.get("content", "")

        agent_loop.register_tool(name, info, execute)
