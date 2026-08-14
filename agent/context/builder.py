from __future__ import annotations

import asyncio
import json

from agent.generation.prompting import PromptContext
from shared.contracts.social import SocialMessage
from shared.contracts.turn import AgentExecutionContext


# 统一装配社交轮次的提示词上下文
async def build_social_context(
    service,
    msg: SocialMessage,
    query: str,
    execution: AgentExecutionContext,
    *,
    sender_name: str,
    entity_context: dict | None = None,
) -> PromptContext:
    is_group = execution.chat_type == "group"
    person_id = execution.sender_person_id
    tool_context = execution.tool_context()
    sender_identity = service.prompt_assembler.render(
        "social-sender-identity",
        sender_name=json.dumps(str(sender_name), ensure_ascii=False),
    )
    relationship_summary = service.prompt_assembler.template("unknown-relationship")
    if person_id:
        try:
            relation = await service.bus.request_json(
                "relationship.summary.request",
                {"ai_id": service.ai_id, "person_id": person_id},
                timeout=float(service._timeouts["relationship_summary_sec"]),
            )
            relationship_summary = str(relation.get("summary", relationship_summary))
        except Exception:
            pass
    if is_group:
        memory_context = await service.memory.person_context(person_id, tool_context)
        memories: list[str] = []
        person_document = "\n".join(
            f"- {item['content']}"
            for item in memory_context.get("facts", [])
            if item.get("content")
        )
        self_document = ""
    else:
        memories, memory_context = await asyncio.gather(
            service.memory.search(query, person_id=person_id),
            service.memory.context(
                person_id=person_id,
                conversation_id=execution.conversation_id,
            ),
        )
        self_document = str(memory_context.get("self_markdown") or "")
        person_document = str(memory_context.get("person_markdown") or "")
    history_limit = int(service.gcfg.get("social", "prompt_history_messages"))
    recent = tuple(
        f"{role}: {content}"
        for role, content in list(
            service.conversation.window(msg.chat.chat_type.value, msg.chat.chat_id)
        )[-(history_limit + 1):-1]
    )
    return PromptContext(
        scene="social-private" if msg.chat.chat_type.value == "private" else "social-group",
        user_input=query,
        relationship_summary=f"{sender_identity}{relationship_summary}",
        memories=tuple(memories),
        self_document=self_document,
        person_document=person_document,
        conversation_summary=str(memory_context.get("conversation_summary") or ""),
        recent_messages=recent,
        entity_context=json.dumps(entity_context or {}, ensure_ascii=False),
    )
