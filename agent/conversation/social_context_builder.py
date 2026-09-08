from __future__ import annotations

import asyncio
import json

from agent.conversation.conversation_context import format_entries, format_group_entries
from agent.conversation.prompt_assembler import PromptContext
from shared.contracts.entity import EntityContext
from shared.contracts.rpc.relationship import RelationshipSummaryRequest, RelationshipSummaryResponse
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
    entity_context: EntityContext,
) -> PromptContext:
    is_group = execution.chat_type == "group"
    person_id = execution.sender_person_id
    tool_context = execution.tool_context()
    sender_identity = service.prompt_assembler.render(
        "social-sender-identity",
        sender_name=json.dumps(str(sender_name), ensure_ascii=False),
    )
    if is_group:
        people = await _collect_relevant_people(service, execution, entity_context, sender_name, sender_identity)
        memories = await _collect_group_memories(service, query, people)
        relevant_people = _render_relevant_people(people)
        summary = ""
        if person_id:
            memory_context = await service.memory.person_context(person_id, tool_context)
            summary = memory_context.conversation_summary
        relationship_summary = ""
        self_document = ""
        person_document = ""
        conversation_summary = summary
    else:
        memories, memory_context = await asyncio.gather(
            service.memory.search(query, person_id=person_id),
            service.memory.context(
                person_id=person_id,
                conversation_id=execution.conversation_id,
            ),
        )
        self_document = memory_context.self_markdown
        person_document = memory_context.person_markdown
        conversation_summary = memory_context.conversation_summary
        relationship_summary = sender_identity + await _relationship_text(service, person_id)
        relevant_people = ""
    history_limit = service.settings.social.prompt_history_messages
    entries = list(service.conversation.window(msg.chat.chat_type.value, msg.chat.chat_id))[-(history_limit + 1) : -1]
    recent_text = (
        format_group_entries(entries, ai_name=service.persona.name)
        if is_group else format_entries(entries, ai_name=service.persona.name)
    )
    current_input = query if is_group else f"[{service.conversation.format_timestamp(msg.timestamp)}]\n{query}"
    return PromptContext(
        scene="social-private" if msg.chat.chat_type.value == "private" else "social-group",
        user_input=current_input,
        relationship_summary=relationship_summary,
        memories=tuple(memories),
        self_document=self_document,
        person_document=person_document,
        relevant_people=relevant_people,
        conversation_summary=conversation_summary,
        recent_messages=(recent_text,) if recent_text else (),
        entity_context=entity_context.model_dump_json(),
    )


# 收集本轮相关人物
async def _collect_relevant_people(
    service,
    execution: AgentExecutionContext,
    entity_context: EntityContext,
    sender_name: str,
    sender_identity: str,
) -> list[dict]:
    people: dict[str, dict] = {}

    def add(person_id: str, name: str, relevance: str, group_card: str = "") -> None:
        if not person_id:
            return
        item = people.setdefault(
            person_id,
            {"person_id": person_id, "name": name, "relevance": [], "group_card": group_card},
        )
        if relevance not in item["relevance"]:
            item["relevance"].append(relevance)

    if execution.sender_person_id:
        add(execution.sender_person_id, sender_name, "current_sender")
    for reference in entity_context.references:
        if reference.status == "resolved" and reference.person_id:
            add(
                reference.person_id,
                reference.display_name or reference.text,
                "explicit_reference",
            )
    for participant in entity_context.recent_participants:
        add(
            str(participant["person_id"]),
            str(participant["display_name"]),
            "recent_participant",
            str(participant["group_card"]),
        )
    selected = list(people.values())[: service.settings.grounding.relevant_people_limit]
    for item in selected:
        person_id = item["person_id"]
        item["relationship"] = (
            sender_identity if person_id == execution.sender_person_id else await _relationship_text(service, person_id)
        )
        facts = await _person_facts(service, person_id, execution.tool_context())
        item["facts"] = facts
    return selected


# 读取关系摘要
async def _relationship_text(service, person_id: str) -> str:
    relation = await service.bus.request_model(
        "relationship.summary.request",
        RelationshipSummaryRequest(ai_id=service.ai_id, person_id=person_id),
        RelationshipSummaryResponse,
        timeout=service._timeouts.relationship_summary_sec,
    )
    return relation.summary


# 读取人物事实
async def _person_facts(service, person_id: str, tool_context) -> list[dict]:
    memory_context = await service.memory.person_context(person_id, tool_context)
    return [item.model_dump(mode="json") for item in memory_context.facts]


# 按相关人物检索群聊记忆
async def _collect_group_memories(service, query: str, people: list[dict]) -> list[str]:
    memories: list[str] = []
    top_k = service.settings.grounding.group_memory_top_k_per_person
    for item in people:
        found = await service.memory.search(query, top_k=top_k, person_id=item["person_id"])
        memories.extend(str(content) for content in found if content)
    return memories[: service.settings.grounding.group_memory_result_limit]


# 渲染相关人物区块
def _render_relevant_people(people: list[dict]) -> str:
    return json.dumps(people, ensure_ascii=False)
