from __future__ import annotations

from agent.conversation.conversation_context import format_entries
from agent.conversation.prompt_assembler import PromptContext
from shared.contracts.live import InteractionEvent
from shared.contracts.rpc.social import SpeechRequest


# 处理直播
async def handle_live(service, evt: InteractionEvent) -> None:
    chat_key = f"live:{evt.actor.uid}"
    service._current_chat_key = chat_key
    service.conversation.add_user(
        "live",
        str(evt.actor.uid),
        evt.content,
        speaker_id=str(evt.actor.uid),
        speaker_name=evt.actor.name,
        timestamp=evt.timestamp,
    )

    history_limit = service.settings.social.live_prompt_history_messages
    entries = list(service.conversation.window("live", str(evt.actor.uid)))[-(history_limit + 1) : -1]
    recent_text = format_entries(entries, ai_name=service.persona.name)
    current_input = service.prompt_assembler.render(
        "live-input",
        actor_name=evt.actor.name,
        event_type=evt.type.value,
        content=evt.content,
    )
    prompt_context = PromptContext(
        scene="live",
        user_input=f"[{service.conversation.format_timestamp(evt.timestamp)}]\n{current_input}",
        relationship_summary=service.prompt_assembler.render("live-relationship", actor_name=evt.actor.name),
        recent_messages=(recent_text,) if recent_text else (),
    )
    plan = await service.chat_agent.generate_plan(
        service.prompt_assembler.build_system_prompt(prompt_context),
        service.prompt_assembler.build_user_prompt(prompt_context),
        allow_tools=False,
    )
    reply = plan.text
    service.conversation.add_ai("live", str(evt.actor.uid), reply)
    await service.bus.publish_model(
        "ai.speech.request",
        SpeechRequest(
            ai_id=service.ai_id,
            session_id=evt.context_metadata.get("session_id", ""),
            text=reply,
            meta={"emotion": plan.emotion.name, "emotion_intensity": plan.emotion.intensity},
        ),
    )
