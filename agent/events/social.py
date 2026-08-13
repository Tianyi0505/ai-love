
from __future__ import annotations

import json
import logging

from ai.llm.types import ChatMessage
from agent.generation.prompting import PromptContext
from agent.generation.response import ResponsePlan
from shared.contracts.social import ContentType, SocialMessage
from agent.events.registry import event_registry

logger = logging.getLogger("ailove.ai-agent.events.social")


@event_registry.register("social")
async def handle_social(service, payload: bytes) -> None:
    msg = SocialMessage.from_dict(json.loads(payload))
    logger.info("[ai-agent:%s] 收到社交: %s: %s", service.ai_id, msg.sender.user_id, msg.text[:30])
    understood = await service.understanding.understand(msg)
    query = understood or msg.text
    if msg.type == ContentType.IMAGE and msg.all_media_urls():
        service.spawn(service.collect_stickers(msg.all_media_urls()))
    is_group = msg.chat.chat_type.value == "group"
    persona = service.persona
    sender_name = persona.name_for(msg.sender.user_id) or msg.sender.name or msg.sender.user_id
    speaker = {
        "person_id": str(msg.meta.get("person_id", "")),
        "platform_user_id": str(msg.sender.user_id),
        "display_name": str(sender_name),
    }
    attributed_query = (
        f"[speaker] {json.dumps(speaker, ensure_ascii=False, separators=(',', ':'))}\n"
        f"[message] {query}"
    )
    if is_group:
        if query:
            service.conversation.add_user("group", msg.chat.chat_id, attributed_query)
        service._observe_group_message(msg.chat.chat_id)
        service._mark_group_replied(msg.chat.chat_id)
    else:
        service.sessions.mark_replied(f"proactive-private:{msg.sender.user_id}")

    relationship_request = {
        "ai_id": service.ai_id,
        "person_id": msg.meta.get("person_id", ""),
        "platform_user_id": msg.sender.user_id,
        "account_id": msg.account_id,
        "chat_type": msg.chat.chat_type.value,
        "group_id": msg.chat.chat_id if is_group else "",
        "quality": 0.0,
    }
    service.spawn(
        service.bus.request_json(
            "relationship.chat.request",
            relationship_request,
            timeout=float(service._timeouts["relationship_update_sec"]),
        )
    )

    explicitly_addressed = bool(
        is_group and (msg.to_ai or (msg.at_user_id and msg.at_user_id == service.ai_id))
    )
    group_turn_started = False
    if is_group:
        group_turn_started = await service._begin_group_turn(
            msg.chat.chat_id,
            force=explicitly_addressed,
        )
        if not group_turn_started:
            logger.info("[ai-agent:%s] 不回复（群聊回合占用或冷却）", service.ai_id)
            return

    if explicitly_addressed:
        should_respond = await service._join_group_checker(
            msg.chat.chat_id,
            explicitly_addressed=True,
        )
    else:
        should_respond = await service.persona.should_respond(
            msg.chat.chat_type.value, msg.to_ai, msg.at_user_id, service.ai_id,
            chat_id=msg.chat.chat_id, join_checker=getattr(service, "join_checker", None),
        )
    if not should_respond:
        if group_turn_started:
            service._finish_group_turn(msg.chat.chat_id)
        logger.info("[ai-agent:%s] 不回复（策略）", service.ai_id)
        return
    if not is_group:
        service.conversation.add_user(msg.chat.chat_type.value, msg.chat.chat_id, attributed_query)
    service._current_chat_key = f"{msg.chat.chat_type.value}:{msg.chat.chat_id}"

    sender_identity = service.prompt_assembler.render(
        "social-sender-identity",
        user_id=json.dumps(str(msg.sender.user_id), ensure_ascii=False),
        sender_name=json.dumps(str(sender_name), ensure_ascii=False),
    )
    relationship_summary = service.prompt_assembler.template("unknown-relationship")
    if msg.meta.get("person_id"):
        try:
            relation = await service.bus.request_json(
                "relationship.summary.request",
                {"ai_id": service.ai_id, "person_id": msg.meta["person_id"]},
                timeout=float(service._timeouts["relationship_summary_sec"]),
            )
            relationship_summary = str(relation.get("summary", relationship_summary))
        except Exception:
            pass
    memories = await service.memory.search(query, person_id=speaker["person_id"])
    history_limit = int(service.gcfg.get("social", "prompt_history_messages"))
    recent = tuple(
        f"{role}: {content}"
        for role, content in list(service.conversation.window(msg.chat.chat_type.value, msg.chat.chat_id))[-(history_limit + 1):-1]
    )
    prompt_context = PromptContext(
        scene="social-private" if msg.chat.chat_type.value == "private" else "social-group",
        user_input=query,
        relationship_summary=f"{sender_identity}{relationship_summary}",
        memories=tuple(memories),
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
        full_reply = ""
    if not full_reply:
        full_reply = (
            service._fallbacks["private_response"]
            if msg.chat.chat_type.value == "private"
            else service._fallbacks["response"]
        )

    plan = ResponsePlan.from_model_output(full_reply)
    if not plan.speech:
        plan = ResponsePlan.from_model_output(service._fallbacks["response"])

    sticker_to_send = None
    reply = plan.text
    voice_sent = False
    sticker_actions = [action for action in plan.actions if action.type == "sticker"]
    if sticker_actions:
        sticker_query = str(sticker_actions[0].params.get("query") or "").strip()
        if not sticker_query:
            sticker_query = f"{query}\nAI回复：{reply}\n情绪：{plan.emotion.name}"
        sticker_to_send = await service.stickers.search(sticker_query)
    send_payload = {
        "ai_id": service.ai_id,
        "account_id": msg.account_id,
        "conversation_id": msg.meta.get("conversation_id", ""),
        "channel": msg.platform or "qq",
        "chat": msg.chat.to_dict(),
        "type": "text",
        "text": reply,
    }
    if sticker_to_send:
        send_payload["sticker"] = sticker_to_send
    wants_voice = any(speech.delivery == "voice" for speech in plan.speech)
    if service.gcfg.get("qq", "voice_reply") and wants_voice:
        voice = await service.tts.synthesize(reply)
        if voice:
            send_payload["voice"] = voice
            voice_sent = True
    send_timeout = float(service.gcfg.get("social", "send_timeout_sec"))
    try:
        send_result = await service.bus.request_json(
            "social.send.request",
            send_payload,
            timeout=send_timeout,
        )
    except Exception as exc:
        send_result = {"ok": False, "fallback_note": str(exc) or "发送确认超时"}

    sticker_sent = bool(sticker_to_send and send_result.get("ok"))
    if sticker_to_send and not send_result.get("ok"):
        fallback_payload = dict(send_payload)
        fallback_payload.pop("sticker", None)
        try:
            send_result = await service.bus.request_json(
                "social.send.request",
                fallback_payload,
                timeout=send_timeout,
            )
        except Exception as exc:
            send_result = {"ok": False, "fallback_note": str(exc) or "发送确认超时"}

    if not send_result.get("ok"):
        if group_turn_started:
            service._finish_group_turn(msg.chat.chat_id)
        logger.warning(
            "[ai-agent:%s] 回复发送失败: %s",
            service.ai_id,
            send_result.get("fallback_note", "unknown"),
        )
        return

    if sticker_sent:
        service.spawn(
            service.bus.request_json(
                "sticker.boost.request",
                {"ai_id": service.ai_id, "sticker_id": sticker_to_send.get("id", "")},
                timeout=float(service._timeouts["sticker_boost_sec"]),
            )
        )
    if is_group:
        service._activate_group_session(msg.chat.chat_id)
        service._mark_group_spoke(msg.chat.chat_id)
        service._finish_group_turn(msg.chat.chat_id)

    remembered = f"[语音] {reply}" if voice_sent else reply
    service.conversation.add_ai(msg.chat.chat_type.value, msg.chat.chat_id, remembered)
    mode = ("语音" if voice_sent else "") + ("+表情" if sticker_sent else "") + ("+文字" if reply and not voice_sent else "")
    logger.info("[ai-agent:%s] 回复 %s [%s]: %s", service.ai_id, msg.sender.name, mode or "文字", reply[:40])
