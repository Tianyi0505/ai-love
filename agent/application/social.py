from __future__ import annotations

import json
import logging

from ai.llm.types import ChatMessage
from agent.context.builder import build_social_context
from agent.generation.response import ResponsePlan
from shared.contracts.entity import EntityContext
from shared.contracts.social import ContentType, SocialMessage
from shared.contracts.turn import AgentExecutionContext, ResponseCommand

logger = logging.getLogger("ailove.ai-agent.events.social")


# 处理社交
async def handle_social(service, payload: bytes) -> None:
    msg = SocialMessage.from_dict(json.loads(payload))
    logger.info("[ai-agent:%s] 收到社交: %s: %s", service.ai_id, msg.sender.user_id, msg.text[:30])
    execution = AgentExecutionContext.from_social_message(msg, service.ai_id)
    run_repo = service.run_repo
    if run_repo is not None:
        try:
            await run_repo.start_run(execution)
        except Exception:
            logger.exception("[ai-agent:%s] 开启执行记录失败: %s", service.ai_id, execution.run_id)
            run_repo = None
    result = await _process_turn(service, msg, execution, run_repo)
    if run_repo is not None:
        try:
            await run_repo.finish_run(
                execution.run_id,
                result["outcome"],
                tool_rounds=result["tool_rounds"],
                response_text=result["response_text"],
            )
        except Exception:
            logger.exception("[ai-agent:%s] 结束执行记录失败: %s", service.ai_id, execution.run_id)


# 处理单个社交轮次
async def _process_turn(service, msg, execution, run_repo) -> dict:
    try:
        return await _process(service, msg, execution, run_repo)
    except Exception:
        logger.exception("[ai-agent:%s] 轮次处理失败: %s", service.ai_id, execution.run_id)
        return {"outcome": "failed", "tool_rounds": 0, "response_text": ""}


# 提取引用消息元信息
def _quote_meta(msg) -> dict | None:
    if msg.quote_ref is None:
        return None
    return {"name": msg.quote_ref.sender.name or msg.quote_ref.sender.user_id}


# 执行回复决策与生成
async def _process(service, msg, execution, run_repo) -> dict:
    outcome = "no_response"
    tool_rounds = 0
    response_text = ""
    step_index = 0

    # 记录执行步骤
    async def record_step(step_type, content=None, status="ok", duration_ms=0, error=""):
        nonlocal step_index
        if run_repo is None:
            return
        index = step_index
        step_index += 1
        try:
            await run_repo.record_step(
                execution.run_id,
                index,
                step_type,
                status=status,
                content=content or {},
                duration_ms=duration_ms,
                error=error,
            )
        except Exception:
            logger.exception("[ai-agent:%s] 记录执行步骤失败", service.ai_id)

    understood = await service.understanding.understand(msg)
    query = understood or msg.text
    if msg.type == ContentType.IMAGE and msg.all_media_urls():
        service.spawn(service.collect_stickers(msg.all_media_urls()))
    is_group = msg.chat.chat_type.value == "group"
    persona = service.persona
    sender_name = persona.name_for(msg.sender.user_id) or msg.sender.name or msg.sender.user_id
    person_id = execution.sender_person_id
    tool_context = execution.tool_context()
    attributed_query = query
    quote_meta = _quote_meta(msg)
    if is_group:
        if query:
            service.conversation.add_user(
                "group",
                msg.chat.chat_id,
                attributed_query,
                speaker_id=person_id,
                speaker_name=sender_name,
                quote=quote_meta,
            )
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
            return {"outcome": "group_turn_busy", "tool_rounds": 0, "response_text": ""}

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
        return {"outcome": "policy_no_response", "tool_rounds": 0, "response_text": ""}

    if not is_group:
        service.conversation.add_user(
            msg.chat.chat_type.value,
            msg.chat.chat_id,
            attributed_query,
            speaker_id=person_id,
            speaker_name=sender_name,
            quote=quote_meta,
        )
    service._current_chat_key = f"{msg.chat.chat_type.value}:{msg.chat.chat_id}"

    entity_context = EntityContext.from_dict(msg.meta.get("entity_context"))
    prompt_context = await build_social_context(
        service,
        msg,
        query,
        execution,
        sender_name=sender_name,
        entity_context=entity_context.to_dict(),
    )
    await record_step("context", {
        "scene": prompt_context.scene,
        "input_chars": len(query),
        "mentions": len(entity_context.references),
        "recent_participants": len(entity_context.recent_participants),
        "recent_messages": len(prompt_context.recent_messages),
        "memories": len(prompt_context.memories),
        "has_self_document": bool(prompt_context.self_document),
        "has_person_document": bool(prompt_context.person_document),
        "has_conversation_summary": bool(prompt_context.conversation_summary),
    })

    history_msgs = [
        ChatMessage(role="system", content=service.prompt_assembler.build_system_prompt(prompt_context)),
        ChatMessage(role="user", content=service.prompt_assembler.build_user_prompt(prompt_context)),
    ]

    # 上报循环内工具与最终生成步骤
    async def on_step(_index: int, kind: str, data: dict) -> None:
        nonlocal tool_rounds
        if kind == "tool":
            tool_rounds += 1
        await record_step(kind, data)

    try:
        full_reply = await service.agent_loop.run(
            history_msgs,
            tool_context=tool_context,
            on_step=on_step,
        )
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

    wants_voice = any(speech.delivery == "voice" for speech in plan.speech)
    voice = None
    if service.gcfg.get("qq", "voice_reply") and wants_voice:
        voice = await service.tts.synthesize(reply)
        if voice:
            voice_sent = True

    command = ResponseCommand(
        run_id=execution.run_id,
        ai_id=service.ai_id,
        account_id=msg.account_id,
        conversation_id=execution.conversation_id,
        platform=msg.platform or "qq",
        chat=msg.chat.to_dict(),
        reply_to_message_id=execution.reply_to_message_id,
        text=reply,
        sticker=sticker_to_send,
        voice=voice,
    )
    send_result = await service.send_response(command)
    sticker_sent = bool(sticker_to_send and send_result.get("ok"))
    if sticker_to_send and not sticker_sent:
        send_result = await service.send_response(command.without_sticker())

    await record_step("send", {
        "ok": bool(send_result.get("ok")),
        "text_chars": len(reply),
        "voice": voice_sent,
        "sticker": sticker_sent,
        "fallback_note": send_result.get("fallback_note", ""),
    })

    if not send_result.get("ok"):
        if group_turn_started:
            service._finish_group_turn(msg.chat.chat_id)
        logger.warning(
            "[ai-agent:%s] 回复发送失败: %s",
            service.ai_id,
            send_result.get("fallback_note", "unknown"),
        )
        return {"outcome": "send_failed", "tool_rounds": tool_rounds, "response_text": reply}

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
    return {"outcome": "sent", "tool_rounds": tool_rounds, "response_text": reply}
