from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Awaitable, Callable

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.conversation_context import ConversationContext
from agent.conversation.prompt_assembler import PromptAssembler, PromptContext
from agent.memory_client import MemoryClient
from agent.persona import Persona
from shared import private_reply_observability as private_metrics
from shared.contracts.agent import ProactiveConfig
from shared.contracts.behavior import BehaviorSchedule
from shared.contracts.rpc.relationship import (
    PersonRelationshipRecord,
    RelationshipListRequest,
    RelationshipListResponse,
)
from shared.contracts.rpc.social import (
    SocialSendResponse,
    SocialSendStatusRequest,
    SocialSendStatusResponse,
)
from shared.contracts.social import Chat, ChatType
from shared.contracts.turn import ResponseCommand, new_run_id
from shared.nats_bus import Bus
from shared.private_interaction_repository import PrivateInteractionRepository

logger = logging.getLogger("ailove.ai-agent.proactive-private")


class ProactivePrivateService:
    def __init__(
        self,
        *,
        ai_id: str,
        default_account_id: str,
        bus: Bus,
        relationship_timeout_sec: float,
        interactions: PrivateInteractionRepository,
        allowed_account_ids: tuple[str, ...],
        conversation: ConversationContext,
        memory: MemoryClient,
        persona: Persona,
        prompt_assembler: PromptAssembler,
        chat_agent: ChatAgent,
        proactive: ProactiveConfig,
        behavior_schedule: BehaviorSchedule,
        send_response: Callable[[ResponseCommand], Awaitable[SocialSendResponse]],
    ) -> None:
        self._ai_id = ai_id
        self._default_account_id = default_account_id
        self._bus = bus
        self._relationship_timeout_sec = relationship_timeout_sec
        self._interactions = interactions
        self._allowed_account_ids = allowed_account_ids
        self._conversation = conversation
        self._memory = memory
        self._persona = persona
        self._prompt_assembler = prompt_assembler
        self._chat_agent = chat_agent
        self._proactive = proactive
        self._behavior_schedule = behavior_schedule
        self._send_response = send_response

    async def loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[ai-agent:%s] 主动私聊检查失败: %s", self._ai_id, exc)
            await asyncio.sleep(self._proactive.private_interval_sec)

    async def run_once(self, now: dt.datetime | None = None) -> bool:
        if not self._proactive.enabled or not self._behavior_schedule.allows_proactive(now):
            return False

        current = now or dt.datetime.now(dt.timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=dt.timezone.utc)
        current = current.astimezone(dt.timezone.utc)
        response = await self._bus.request_model(
            "relationship.list.request",
            RelationshipListRequest(ai_id=self._ai_id),
            RelationshipListResponse,
            timeout=self._relationship_timeout_sec,
        )
        candidates = sorted(
            (item for item in response.relationships if self._eligible(item, current)),
            key=lambda item: (item.priority_contact, item.familiarity + item.importance),
            reverse=True,
        )
        logger.info(
            "[ai-agent:%s] 主动私聊检查: 联系人=%d 候选=%d",
            self._ai_id,
            len(response.relationships),
            len(candidates),
        )
        for candidate in candidates:
            state = await self._interactions.state(self._ai_id, candidate.person_id)
            if state is None or state.status != "active" or state.pending_run_id or state.unanswered_count >= 3:
                continue
            if state.last_success_at and (current - state.last_success_at).total_seconds() < self._proactive.private_cooldown_sec:
                continue
            return await self._contact(candidate, state, current)
        return False

    @staticmethod
    def session_key(user_id: str) -> str:
        return f"proactive-private:{user_id}"

    def _eligible(self, relationship: PersonRelationshipRecord, now: dt.datetime) -> bool:
        if relationship.account_id not in self._allowed_account_ids or not relationship.user_id:
            return False
        if relationship.familiarity + relationship.importance < self._proactive.private_min_weight:
            return False
        last_interaction = relationship.last_interaction_at
        if last_interaction is None:
            return True
        if last_interaction.tzinfo is None:
            last_interaction = last_interaction.replace(tzinfo=dt.timezone.utc)
        elapsed = now - last_interaction.astimezone(dt.timezone.utc)
        return elapsed.total_seconds() >= self._proactive.private_quiet_period_sec

    async def _contact(self, relationship: PersonRelationshipRecord, state, current: dt.datetime) -> bool:
        name = self._persona.name_for(relationship.user_id) or relationship.display_name or "朋友"
        memory_context = await self._memory.context(person_id=relationship.person_id)
        context = PromptContext(
            scene="proactive-private",
            user_input=self._prompt_assembler.render("proactive-private-input", name=name),
            relationship_summary=self._prompt_assembler.render(
                "proactive-private-relationship",
                name=name,
                familiarity=f"{relationship.familiarity:.2f}",
                affinity=f"{relationship.affinity:.2f}",
                trust=f"{relationship.trust:.2f}",
                importance=f"{relationship.importance:.2f}",
            ),
            self_document=memory_context.self_markdown,
            person_document=memory_context.person_markdown,
            conversation_summary=memory_context.conversation_summary,
        )
        plan = await self._chat_agent.generate_plan(
            self._prompt_assembler.build_system_prompt(context),
            self._prompt_assembler.build_user_prompt(context),
            allow_tools=False,
        )
        text = plan.text.strip()
        if not text:
            private_metrics.proactive("skipped", "empty")
            logger.info("[ai-agent:%s] 主动私聊跳过: 与 %s 暂无自然话题", self._ai_id, name)
            return False

        if not self._behavior_schedule.allows_proactive(current):
            private_metrics.proactive("skipped", "schedule")
            return False
        run_id = new_run_id()
        if not await self._interactions.reserve(self._ai_id, relationship.person_id, run_id, state.revision,
                                               self._proactive.private_cooldown_sec,
                                               self._proactive.private_quiet_period_sec):
            private_metrics.proactive("skipped", "stale")
            return False
        account_id = relationship.account_id
        command = ResponseCommand(
                run_id=run_id,
                delivery_kind="proactive_private",
                person_id=relationship.person_id,
                ai_id=self._ai_id,
                account_id=account_id,
                conversation_id="",
                platform="qq",
                chat=Chat(
                    chat_id=relationship.user_id,
                    chat_type=ChatType.PRIVATE,
                    chat_name=name,
                ).model_dump(mode="json"),
                reply_to_message_id="",
                text=text,
                sticker=None,
                voice=None,
            )
        try:
            await self._send_response(command)
        except Exception as exc:
            try:
                status = await self._bus.request_model(
                    "social.send.status.request",
                    SocialSendStatusRequest(ai_id=self._ai_id, account_id=account_id, run_id=run_id),
                    SocialSendStatusResponse,
                    timeout=self._relationship_timeout_sec,
                )
            except Exception:
                status = SocialSendStatusResponse(status="unknown")
            if status.status != "sent":
                if status.status not in ("failed",) or status.retryable:
                    await self._interactions.mark_pending_unknown(
                        self._ai_id, relationship.person_id, run_id, type(exc).__name__
                    )
                private_metrics.proactive("unknown" if status.status != "failed" else "failed", status.status)
                return False
        self._conversation.add_ai(ChatType.PRIVATE.value, relationship.user_id, text)
        private_metrics.proactive("sent")
        logger.info("[ai-agent:%s] 主动私聊已确认: person_id=%s", self._ai_id, relationship.person_id)
        return True
