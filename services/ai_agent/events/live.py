
from __future__ import annotations

import json
import logging

from services.ai_agent.llm.service import ChatMessage
from services.ai_agent.prompting import PromptContext
from shared.contracts.live import InteractionEvent
from shared.contracts.response import ResponsePlan
from services.ai_agent.events.registry import event_registry

logger = logging.getLogger("ailove.ai-agent.events.live")


@event_registry.register("live_event")
async def handle_live(service, payload: bytes) -> None:
    evt = InteractionEvent.from_dict(json.loads(payload))
    chat_key = f"live:{evt.actor.uid}"
    service._current_chat_key = chat_key
    service.conversation.add_user("live", str(evt.actor.uid), evt.content)

    recent = tuple(
        f"{role}: {content}"
        for role, content in list(service.conversation.window("live", str(evt.actor.uid)))[-8:-1]
    )
    actors = "、".join(evt.context_metadata.get("active_actors", []))
    prompt_context = PromptContext(
        scene="live",
        user_input=f"观众{evt.actor.name}发来{evt.type.value}：{evt.content}",
        relationship_summary=f"当前观众：{evt.actor.name}",
        recent_messages=recent,
        director_instruction=f"当前同台阵容：{actors or service.persona.name}。现在轮到你回应。",
    )
    history_msgs = [
        ChatMessage(role="system", content=service.prompt_assembler.build_system_prompt(prompt_context)),
        ChatMessage(role="user", content=service.prompt_assembler.build_user_prompt(prompt_context)),
    ]

    try:
        full_reply = await service.agent_loop.run(history_msgs)
    except Exception as e:
        logger.warning("[ai-agent:%s] LLM 失败: %s", service.ai_id, e)
        full_reply = "嗯嗯，我在听～"
    plan = ResponsePlan.from_model_output(full_reply)
    reply = plan.text or "嗯嗯，我在听～"
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
