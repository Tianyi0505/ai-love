from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.conversation_context import ConversationContext, format_group_entries, group_entries
from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.prompt_assembler import PromptAssembler, PromptContext
from agent.conversation.session_manager import SessionManager
from agent.persona import Persona
from agent.social.group_chat_manager import GroupChatManager
from shared.contracts.agent import ProactiveConfig
from shared.contracts.behavior import BehaviorSchedule
from shared.contracts.rpc.relationship import (
    GroupRelationshipData,
    GroupRelationshipRequest,
    GroupRelationshipResponse,
)
from shared.nats_bus import Bus

logger = logging.getLogger("ailove.ai-agent.group-participation")


class GroupParticipationService:
    def __init__(
        self,
        *,
        ai_id: str,
        account_id: str,
        bus: Bus,
        relationship_timeout_sec: float,
        sessions: SessionManager,
        conversation: ConversationContext,
        persona: Persona,
        prompt_assembler: PromptAssembler,
        chat_agent: ChatAgent,
        proactive: ProactiveConfig,
        behavior_schedule: BehaviorSchedule,
        group_whitelist: Sequence[str | int],
    ) -> None:
        self._ai_id = ai_id
        self._account_id = account_id
        self._bus = bus
        self._relationship_timeout_sec = relationship_timeout_sec
        self._sessions = sessions
        self._conversation = conversation
        self._persona = persona
        self._prompt_assembler = prompt_assembler
        self._chat_agent = chat_agent
        self._proactive = proactive
        self._behavior_schedule = behavior_schedule
        self._group_whitelist = frozenset(str(group_id) for group_id in group_whitelist)
        self._manager = GroupChatManager()
        self._turns_in_flight: dict[str, float] = {}

    def observe(self, chat_id: str) -> None:
        self._manager.observe(
            chat_id,
            join_window_sec=self._proactive.group_join_window_sec,
            idle_sec=self._proactive.group_session_idle_sec,
            max_active_sec=self._proactive.group_session_max_sec,
            rest_sec=self._proactive.group_session_rest_sec,
        )

    def activate(self, chat_id: str) -> None:
        self._manager.activate(chat_id)

    async def mark_spoke(self, chat_id: str) -> None:
        await self._sessions.mark_spoke(f"group:{chat_id}")

    async def mark_replied(self, chat_id: str) -> None:
        await self._sessions.mark_replied(f"group:{chat_id}")

    async def begin_turn(
        self,
        chat_id: str,
        *,
        force: bool,
    ) -> bool:
        now = time.monotonic()
        started_at = self._turns_in_flight.get(chat_id)
        if started_at is not None and now - started_at < self._proactive.group_turn_in_flight_sec:
            return False
        if not force:
            relationship = await self._relationship(chat_id)
            participation_score = self._participation_score(relationship)
            cooldown_sec = self._cooldown(participation_score)
            if not await self._sessions.can_initiate(f"group:{chat_id}", cooldown_sec):
                return False
        self._turns_in_flight[chat_id] = now
        return True

    def finish_turn(self, chat_id: str) -> None:
        self._turns_in_flight.pop(chat_id, None)

    async def should_join(
        self,
        chat_id: str,
        *,
        explicitly_addressed: bool,
        images: Sequence[ImageAttachment] = (),
    ) -> bool:
        if not explicitly_addressed and (
            not self._proactive.enabled
            or (chat_id not in self._group_whitelist and not self._behavior_schedule.allows_proactive())
        ):
            logger.info("[ai-agent:%s] 群聊跳过: 非工作时段/未启用", self._ai_id)
            return False

        session = self._manager.session(chat_id)
        ready = self._manager.ready_to_join(chat_id, self._proactive.group_join_min_messages)
        logger.info(
            "[ai-agent:%s] 群聊判断: active=%s ready=%s recent=%d",
            self._ai_id,
            session.active,
            ready,
            len(session.recent_messages),
        )
        if not explicitly_addressed and not session.active and not ready:
            return False

        recent = list(self._conversation.window("group", chat_id))[-self._proactive.group_join_history_messages :]
        if not recent:
            logger.info("[ai-agent:%s] 群聊跳过: 会话窗口空", self._ai_id)
            return False

        ai_name = self._persona.name
        current_message = json.dumps(group_entries([recent[-1]], ai_name)[0], ensure_ascii=False)
        history_text = format_group_entries(recent[:-1], ai_name)
        relationship = await self._relationship(chat_id)
        score = self._participation_score(relationship)
        logger.info(
            "[ai-agent:%s] 群聊判断: score=%.3f 门槛=%.2f",
            self._ai_id,
            score,
            self._proactive.group_min_score,
        )
        if not explicitly_addressed and score < self._proactive.group_min_score:
            return False

        session_state = self._prompt_assembler.template(
            "group-join-session-active" if session.active else "group-join-session-inactive"
        )
        context = PromptContext(
            scene="group-join",
            user_input=current_message,
            extra={"提及状态": "当前真实消息明确 @ 了你" if explicitly_addressed else "当前群聊消息"},
            recent_messages=(history_text,) if history_text else (),
            relationship_summary=self._prompt_assembler.render(
                "group-join-relationship",
                familiarity=f"{relationship.familiarity:.2f}",
                belonging=f"{relationship.belonging:.2f}",
                affinity=f"{relationship.affinity:.2f}",
                activity_willingness=f"{relationship.activity_willingness:.2f}",
                score=f"{score:.2f}",
                session_state=session_state,
            ),
            output_protocol=self._prompt_assembler.template("participation-output"),
        )
        decision = await self._chat_agent.decide_participation(
            self._prompt_assembler.build_system_prompt(context),
            self._prompt_assembler.build_user_prompt(context),
            images=images,
        )
        return decision.participate

    async def _relationship(self, chat_id: str) -> GroupRelationshipData:
        response = await self._bus.request_model(
            "relationship.group.request",
            GroupRelationshipRequest(
                ai_id=self._ai_id,
                account_id=self._account_id,
                group_id=chat_id,
            ),
            GroupRelationshipResponse,
            timeout=self._relationship_timeout_sec,
        )
        return response.relationship

    def _participation_score(self, relationship: GroupRelationshipData) -> float:
        weights = self._proactive.group_participation_weights
        return (
            relationship.activity_willingness * weights.activity_willingness
            + relationship.belonging * weights.belonging
            + relationship.affinity * weights.affinity
            + relationship.familiarity * weights.familiarity
        )

    def _cooldown(self, participation_score: float) -> int:
        minimum = self._proactive.group_min_cooldown_sec
        maximum = self._proactive.group_max_cooldown_sec
        return round(
            minimum
            + (maximum - minimum)
            * (self._proactive.participation_score_ceiling - participation_score)
            ** self._proactive.group_cooldown_curve_exponent
        )
