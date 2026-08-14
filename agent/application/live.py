
from __future__ import annotations

import json
import logging

from ai.llm.types import ChatMessage
from agent.generation.prompting import PromptContext
from shared.contracts.live import InteractionEvent
from agent.generation.response import ResponsePlan

logger = logging.getLogger("ailove.ai-agent.events.live")


# 处理直播
async def handle_live(service, payload: bytes) -> None:
    evt = InteractionEvent.from_dict(json.loads(payload))
    chat_key = f"live:{evt.actor.uid}"
    service._current_chat_key = chat_key
    service.conversation.add_user("live", str(evt.actor.uid), evt.content)

    history_limit = int(service.gcfg.get("social", "live_prompt_history_messages"))
    recent = tuple(
        f"{role}: {content}"
        for role, content, _meta in list(service.conversation.window("live", str(evt.actor.uid)))[-(history_limit + 1):-1]
    )
    prompt_context = PromptContext(
        scene="live",
        user_input=service.prompt_assembler.render(
            "live-input",
            actor_name=evt.actor.name,
            event_type=evt.type.value,
            content=evt.content,
        ),
        relationship_summary=service.prompt_assembler.render(
            "live-relationship", actor_name=evt.actor.name
        ),
        recent_messages=recent,
    )
    history_msgs = [
        ChatMessage(role="system", content=service.prompt_assembler.build_system_prompt(prompt_context)),
        ChatMessage(role="user", content=service.prompt_assembler.build_user_prompt(prompt_context)),
    ]

    try:
        full_reply = await service.agent_loop.run(history_msgs)
    except Exception as e:
        logger.warning("[ai-agent:%s] LLM 失败: %s", service.ai_id, e)
        full_reply = service._fallbacks["response"]
    plan = ResponsePlan.from_model_output(full_reply)
    reply = plan.text or service._fallbacks["response"]
    service.conversation.add_ai("live", str(evt.actor.uid), reply)
    await service.bus.publish_json(
        "ai.speech.request",
        {
            "ai_id": service.ai_id,
            "session_id": evt.context_metadata.get("session_id", ""),
            "text": reply,
            "meta": {"emotion": plan.emotion.name, "emotion_intensity": plan.emotion.intensity},
        },
    )
    logger.info("[ai-agent:%s] 直播回应 %s: %s", service.ai_id, evt.actor.name, reply[:40])
