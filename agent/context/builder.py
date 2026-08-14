from __future__ import annotations

import asyncio
import json

from agent.context.conversation import format_entries
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
    if is_group:
        people = await _collect_relevant_people(
            service, execution, entity_context, sender_name, sender_identity
        )
        memories = await _collect_group_memories(service, query, people)
        relevant_people = _render_relevant_people(people)
        summary = ""
        if person_id:
            memory_context = await service.memory.person_context(person_id, tool_context)
            summary = str(memory_context.get("conversation_summary") or "")
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
        self_document = str(memory_context.get("self_markdown") or "")
        person_document = str(memory_context.get("person_markdown") or "")
        conversation_summary = str(memory_context.get("conversation_summary") or "")
        relationship_summary = sender_identity + await _relationship_text(service, person_id)
        relevant_people = ""
    history_limit = int(service.gcfg.get("social", "prompt_history_messages"))
    entries = list(
        service.conversation.window(msg.chat.chat_type.value, msg.chat.chat_id)
    )[-(history_limit + 1):-1]
    recent_text = format_entries(entries, ai_name=service.persona.name)
    return PromptContext(
        scene="social-private" if msg.chat.chat_type.value == "private" else "social-group",
        user_input=query,
        relationship_summary=relationship_summary,
        memories=tuple(memories),
        self_document=self_document,
        person_document=person_document,
        relevant_people=relevant_people,
        conversation_summary=conversation_summary,
        recent_messages=(recent_text,) if recent_text else (),
        entity_context=json.dumps(entity_context or {}, ensure_ascii=False),
    )


# 收集本轮相关人物
async def _collect_relevant_people(
    service,
    execution: AgentExecutionContext,
    entity_context: dict | None,
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
    raw = entity_context if isinstance(entity_context, dict) else {}
    for reference in raw.get("references") or []:
        if reference.get("status") == "resolved" and reference.get("person_id"):
            add(
                str(reference.get("person_id") or ""),
                str(reference.get("display_name") or reference.get("text") or ""),
                "explicit_reference",
            )
    for participant in (raw.get("recent_participants") or [])[:2]:
        add(
            str(participant.get("person_id") or ""),
            str(participant.get("display_name") or ""),
            "recent_participant",
            str(participant.get("group_card") or ""),
        )
    selected = list(people.values())[:4]
    for item in selected:
        person_id = item["person_id"]
        item["relationship"] = sender_identity if person_id == execution.sender_person_id else await _relationship_text(service, person_id)
        facts = await _person_facts(service, person_id, execution.tool_context())
        item["facts"] = facts[:5]
    return selected


# 读取关系摘要
async def _relationship_text(service, person_id: str) -> str:
    fallback = service.prompt_assembler.template("unknown-relationship")
    if not person_id:
        return fallback
    try:
        relation = await service.bus.request_json(
            "relationship.summary.request",
            {"ai_id": service.ai_id, "person_id": person_id},
            timeout=float(service._timeouts["relationship_summary_sec"]),
        )
        return str(relation.get("summary", fallback))
    except Exception:
        return fallback


# 读取人物事实
async def _person_facts(service, person_id: str, tool_context) -> list[dict]:
    if not person_id:
        return []
    try:
        memory_context = await service.memory.person_context(person_id, tool_context)
        return [
            item for item in memory_context.get("facts", []) if item.get("content")
        ]
    except Exception:
        return []


# 按相关人物检索群聊记忆
async def _collect_group_memories(service, query: str, people: list[dict]) -> list[str]:
    memories: list[str] = []
    for item in people[:3]:
        try:
            found = await service.memory.search(
                query, top_k=2, person_id=item["person_id"]
            )
        except Exception:
            found = []
        memories.extend(str(content) for content in found if content)
    return memories[:4]


# 渲染相关人物区块
def _render_relevant_people(people: list[dict]) -> str:
    lines: list[str] = []
    for item in people:
        name = item["name"] or item["group_card"] or item["person_id"]
        lines.append(f"- {item['person_id']}（{name}）")
        relevance = "、".join(item["relevance"]) or "相关人物"
        lines.append(f"  相关性：{relevance}")
        lines.append(f"  关系：{item.get('relationship') or ''}")
        facts = item.get("facts") or []
        if facts:
            lines.append("  已知事实：")
            lines.extend(f"  - {fact['content']}" for fact in facts)
    return "\n".join(lines)
