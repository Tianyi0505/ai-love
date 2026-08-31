from __future__ import annotations

import logging

from agent.conversation.social_context_builder import build_social_context
from shared.contracts.entity import EntityContext
from shared.contracts.rpc.relationship import RelationshipChatRequest, RelationshipSummaryResponse
from shared.contracts.rpc.rpc_model import SuccessResponse
from shared.contracts.rpc.sticker import StickerBoostRequest
from shared.contracts.social import ContentType, SocialMessage
from shared.contracts.turn import AgentExecutionContext, ResponseCommand

logger = logging.getLogger("ailove.ai-agent.events.social")


# 处理社交
async def handle_social(service, msg: SocialMessage) -> None:
    preview_chars = service.settings.social.log_preview_chars
    logger.info(
        "[ai-agent:%s] 收到社交: %s: %s",
        service.ai_id,
        msg.sender.user_id,
        msg.text[:preview_chars],
    )
    execution = AgentExecutionContext.from_social_message(msg, service.ai_id)
    await _process(service, msg, execution)


# 提取引用消息元信息
def _quote_meta(msg) -> dict | None:
    if msg.quote_ref is None:
        return None
    return {"name": msg.quote_ref.sender.name or msg.quote_ref.sender.user_id}


# 执行回复决策与生成
async def _process(service, msg, execution) -> dict:
    tool_rounds = 0
    preview_chars = service.settings.social.log_preview_chars

    is_group = msg.chat.chat_type.value == "group"
    should_repeat = is_group and await service.group_repeat.should_repeat(msg)
    if should_repeat:
        query = msg.text
        images = []
    else:
        message_input = await service.message_input.build(msg)
        query = message_input.text or msg.text
        images = message_input.images
    if msg.type == ContentType.IMAGE and msg.all_media_urls():
        service.spawn(service.sticker_collector.collect(msg.all_media_urls()))
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
        service.group_participation.observe(msg.chat.chat_id)
        await service.group_participation.mark_replied(msg.chat.chat_id)
    else:
        await service.sessions.mark_replied(service.proactive_private.session_key(msg.sender.user_id))
    service.spawn(
        service.bus.request_model(
            "relationship.chat.request",
            RelationshipChatRequest(
                ai_id=service.ai_id,
                person_id=str(msg.meta["person_id"]),
                platform_user_id=msg.sender.user_id,
                account_id=msg.account_id,
                chat_type=msg.chat.chat_type.value,
                group_id=msg.chat.chat_id if is_group else "",
                quality=service.definition.relationship_policy.bounds.neutral_quality,
            ),
            RelationshipSummaryResponse,
            timeout=service._timeouts.relationship_update_sec,
        )
    )

    if should_repeat:
        command = ResponseCommand(
            run_id=execution.run_id,
            ai_id=service.ai_id,
            account_id=msg.account_id,
            conversation_id=execution.conversation_id,
            platform=msg.platform,
            chat=msg.chat.model_dump(mode="json"),
            reply_to_message_id="",
            text=attributed_query,
            sticker=None,
            voice=None,
            repeat_message_id=msg.message_id,
        )
        await service.send_response(command)
        service.group_participation.activate(msg.chat.chat_id)
        await service.group_participation.mark_spoke(msg.chat.chat_id)
        service.conversation.add_ai("group", msg.chat.chat_id, attributed_query)
        logger.info(
            "[ai-agent:%s] 群聊 +1: message_id=%s content_hash=%s",
            service.ai_id,
            msg.message_id,
            service.group_repeat.content_hash(msg),
        )
        return {"outcome": "group_repeat", "tool_rounds": 0, "response_text": attributed_query}

    explicitly_addressed = bool(is_group and (msg.to_ai or (msg.at_user_id and msg.at_user_id == service.ai_id)))
    group_turn_started = False
    if is_group:
        group_turn_started = await service.group_participation.begin_turn(
            msg.chat.chat_id,
            force=explicitly_addressed,
        )
        if not group_turn_started:
            logger.info("[ai-agent:%s] 不回复（群聊回合占用或冷却）", service.ai_id)
            return {"outcome": "group_turn_busy", "tool_rounds": 0, "response_text": ""}

    if explicitly_addressed:
        should_respond = await service.group_participation.should_join(
            msg.chat.chat_id,
            explicitly_addressed=True,
            images=images,
        )
    else:
        should_respond = service.persona.should_respond_directly(
            msg.chat.chat_type.value,
            msg.to_ai,
            msg.at_user_id,
            service.ai_id,
        )
        if is_group and not should_respond:
            should_respond = await service.group_participation.should_join(
                msg.chat.chat_id,
                explicitly_addressed=False,
                images=images,
            )
    if not should_respond:
        if group_turn_started:
            service.group_participation.finish_turn(msg.chat.chat_id)
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

    entity_context = EntityContext.model_validate(msg.meta["entity_context"])
    prompt_context = await build_social_context(
        service,
        msg,
        query,
        execution,
        sender_name=sender_name,
        entity_context=entity_context,
    )
    plan = await service.chat_agent.generate_plan(
        service.prompt_assembler.build_system_prompt(prompt_context),
        service.prompt_assembler.build_user_prompt(prompt_context),
        tool_context=tool_context,
        images=images,
    )

    sticker_to_send = None
    reply = plan.text
    voice_sent = False
    sticker_actions = [action for action in plan.actions if action.type == "sticker"]
    if sticker_actions:
        sticker_query = sticker_actions[0].query
        sticker_to_send = await service.stickers.search(sticker_query)

    wants_voice = any(speech.delivery == "voice" for speech in plan.speech)
    voice = None
    if service.settings.qq.voice_reply and wants_voice:
        voice = await service.tts.synthesize(reply)
        voice_sent = True

    command = ResponseCommand(
        run_id=execution.run_id,
        ai_id=service.ai_id,
        account_id=msg.account_id,
        conversation_id=execution.conversation_id,
        platform=msg.platform,
        chat=msg.chat.model_dump(mode="json"),
        reply_to_message_id=execution.reply_to_message_id,
        text=reply,
        sticker=sticker_to_send,
        voice=voice,
    )
    await service.send_response(command)
    sticker_sent = sticker_to_send is not None

    if sticker_sent:
        service.spawn(
            service.bus.request_model(
                "sticker.boost.request",
                StickerBoostRequest(ai_id=service.ai_id, sticker_id=sticker_to_send["id"]),
                SuccessResponse,
                timeout=service._timeouts.sticker_boost_sec,
            )
        )
    if is_group:
        service.group_participation.activate(msg.chat.chat_id)
        await service.group_participation.mark_spoke(msg.chat.chat_id)
        service.group_participation.finish_turn(msg.chat.chat_id)

    remembered = f"[语音] {reply}" if voice_sent else reply
    service.conversation.add_ai(msg.chat.chat_type.value, msg.chat.chat_id, remembered)
    mode = (
        ("语音" if voice_sent else "")
        + ("+表情" if sticker_sent else "")
        + ("+文字" if reply and not voice_sent else "")
    )
    logger.info(
        "[ai-agent:%s] 回复 %s [%s]: %s",
        service.ai_id,
        msg.sender.name,
        mode or "文字",
        reply[:preview_chars],
    )
    return {"outcome": "sent", "tool_rounds": tool_rounds, "response_text": reply}
