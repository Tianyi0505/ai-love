
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from services.ai_agent.agent_loop import AgentLoop
from services.ai_agent.application.conversation import ConversationContext
from services.ai_agent.application.proactive import GroupChatManager, ProactiveChat
from services.ai_agent.application.retrieval import Retrieval
from services.ai_agent.application.session import SessionManager
from services.ai_agent.events.handlers import EventHandlers
from services.ai_agent.llm.providers import anthropic_gw, deepseek, ollama  # noqa: F401
from services.ai_agent.llm.service import ChatMessage, create_llm
from services.ai_agent.memory.manager import MemoryManager
from services.ai_agent.message_understanding import MessageUnderstanding
from services.ai_agent.persona.model import Persona
from services.ai_agent.prompting import PromptAssembler, PromptContext
from services.ai_agent.tools import register_tools
from shared.contracts.agent import AgentDefinition
from shared.contracts.events import TurnRequest
from shared.contracts.response import ResponsePlan
from shared.infrastructure.global_config import GlobalConfig
from shared.vision.base import create_describer

logger = logging.getLogger("ailove.ai-agent")


class AIRuntime:
    def __init__(self, host, definition: AgentDefinition, account_ids: tuple[str, ...] = ()) -> None:
        self._host = host
        self.definition = definition
        self.cfg = host.cfg
        self.bus = host.bus
        self._account_ids = account_ids
        self._tasks: list[asyncio.Task] = []
        self._in_flight = 0
        self._group_turns_in_flight: dict[str, float] = {}

    async def start(self) -> None:
        self.ai_id = self.definition.ai_id

        self.gcfg = GlobalConfig(provider=self.cfg.nacos)
        await self.gcfg.load()
        self.persona = Persona.from_definition(self.definition, self.gcfg)
        self._llm = create_llm(
            self.persona.llm_models,
            timeout_ms=int(self.gcfg.get("llm", "timeout_ms")),
        )

        self.conversation = ConversationContext(
            window_size=int(self.gcfg.get("social", "window_size", 20)),
            data_dir=f"/app/data/agents/{self.ai_id}",
        )

        self.understanding = MessageUnderstanding(
            asr=None,
            image_describer=create_describer(self.gcfg.get("image", "describer", "mcp_default")),
        )

        self.prompt_assembler = PromptAssembler(self.definition)
        self.agent_loop = AgentLoop(self._llm, ai_id=self.ai_id)

        await register_tools(self.agent_loop, self.bus, self.ai_id)

        self.memory = MemoryManager(self.bus, self._llm, self.ai_id, self.gcfg)

        self.retrieval = Retrieval(self)

        self.handlers = EventHandlers(self)

        self.join_checker = self._join_group_checker
        self.sessions = SessionManager(data_dir=f"/app/data/agents/{self.ai_id}")

        self.spawn(self._compensation_loop())

        self._proactive_config = dict(self.definition.behavior_policy.get("proactive", {}))
        self._proactive_enabled = self._proactive_config.get(
            "enabled", self.gcfg.get("proactive", "enabled", True)
        )
        self.group_manager = GroupChatManager()
        self.proactive = ProactiveChat(self.definition.behavior_policy)
        if self._account_ids and self._proactive_enabled:
            self.spawn(self.proactive.loop(
                self,
                int(self._proactive_config.get("private_interval_sec", 1800)),
                float(self._proactive_config.get("min_weight", 0.15)),
            ))
        self.spawn(self.memory.consolidate_loop(self.conversation.all_windows))

    @property
    def primary_social_account_id(self) -> str:
        return self._account_ids[0] if self._account_ids else ""

    async def drain(self) -> None:
        while self._in_flight:
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        task.add_done_callback(self._discard_task)
        return task

    def _discard_task(self, task: asyncio.Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("[ai-agent:%s] 后台任务失败: %s", self.ai_id, task.exception())

    async def handle_social(self, payload: bytes) -> None:
        self._in_flight += 1
        try:
            await self.handlers.on_social(payload)
        finally:
            self._in_flight -= 1

    async def handle_live(self, payload: bytes) -> None:
        self._in_flight += 1
        try:
            await self.handlers.on_event(payload)
        finally:
            self._in_flight -= 1

    async def handle_turn(self, turn: TurnRequest):
        social_message = turn.metadata.get("social_message")
        if social_message:
            await self.handle_social(json.dumps(social_message, ensure_ascii=False).encode("utf-8"))
            return None
        raise ValueError(f"暂不支持的回合来源: {turn.source}")

    async def handle_comment(self, payload: bytes) -> bytes:
        self._in_flight += 1
        try:
            return await self._on_comment_request(payload)
        finally:
            self._in_flight -= 1

    async def _list_personas(self) -> list[dict]:
        try:
            resp = await self.bus.request_json("relationship.list.request", {"ai_id": self.ai_id}, timeout=3.0)
            return resp.get("relationships", [])
        except Exception:
            return []

    async def list_personas(self) -> list[dict]:
        return await self._list_personas()

    async def send_private(self, p: dict) -> None:
        await self._send_proactive(p)

    def _can_speak_in_group(self, chat_id: str, cooldown_sec: int = 0) -> bool:
        chat_key = f"group:{chat_id}"
        if cooldown_sec > 0:
            return self.sessions.can_initiate(chat_key, cooldown_sec)
        return self.sessions.can_speak(chat_key)

    def _mark_group_spoke(self, chat_id: str) -> None:
        self.sessions.mark_spoke(f"group:{chat_id}")

    def _mark_group_replied(self, chat_id: str) -> None:
        self.sessions.mark_replied(f"group:{chat_id}")

    def _observe_group_message(self, chat_id: str) -> None:
        self.group_manager.observe(
            chat_id,
            join_window_sec=int(self._proactive_config.get("group_join_window_sec", 180)),
            idle_sec=int(self._proactive_config.get("group_session_idle_sec", 300)),
            max_active_sec=int(self._proactive_config.get("group_session_max_sec", 1200)),
            rest_sec=int(self._proactive_config.get("group_session_rest_sec", 600)),
        )

    def _activate_group_session(self, chat_id: str) -> None:
        self.group_manager.activate(chat_id)

    async def _begin_group_turn(
        self,
        chat_id: str,
        *,
        force: bool = False,
        relationship: dict | None = None,
    ) -> bool:
        now = time.monotonic()
        started_at = self._group_turns_in_flight.get(chat_id)
        if started_at is not None and now - started_at < 60:
            return False
        if not force:
            relationship = relationship or await self._group_relationship(chat_id)
            score = self._group_participation_score(relationship)
            if not self._can_speak_in_group(chat_id, self._group_cooldown(score)):
                return False
        self._group_turns_in_flight[chat_id] = now
        return True

    def _finish_group_turn(self, chat_id: str) -> None:
        self._group_turns_in_flight.pop(chat_id, None)

    async def _group_relationship(self, chat_id: str) -> dict:
        try:
            response = await self.bus.request_json(
                "relationship.group.request",
                {
                    "ai_id": self.ai_id,
                    "account_id": self.primary_social_account_id,
                    "group_id": chat_id,
                },
                timeout=2.0,
            )
            return dict(response.get("relationship", {}))
        except Exception as exc:
            logger.warning("[ai-agent:%s] 读取群关系失败: %s", self.ai_id, exc)
            return {}

    @staticmethod
    def _group_participation_score(relationship: dict) -> float:
        score = (
            float(relationship.get("activity_willingness", 0.0)) * 0.40
            + float(relationship.get("belonging", 0.0)) * 0.25
            + float(relationship.get("affinity", 0.0)) * 0.20
            + float(relationship.get("familiarity", 0.0)) * 0.15
        )
        return max(0.0, min(1.0, score))

    def _group_cooldown(self, participation_score: float) -> int:
        minimum = int(self._proactive_config.get("group_min_cooldown_sec", 60))
        maximum = int(self._proactive_config.get("group_max_cooldown_sec", 300))
        return round(minimum + (maximum - minimum) * (1.0 - participation_score) ** 2)

    def _limit_sentences(self, text: str, max_sentences: int = 3) -> str:
        sentences = re.split(r"(?<=[。！？!?])", text.strip())
        if len(sentences) <= max_sentences:
            return text
        return "".join(sentences[:max_sentences])

    async def _generate_plan(self, context: PromptContext, fallback: str = "") -> ResponsePlan:
        messages = [
            ChatMessage(role="system", content=self.prompt_assembler.build_system_prompt(context)),
            ChatMessage(role="user", content=self.prompt_assembler.build_user_prompt(context)),
        ]
        try:
            output = await self.agent_loop.run(messages)
        except Exception as exc:
            logger.warning("[ai-agent:%s] 场景 %s 生成失败: %s", self.ai_id, context.scene, exc)
            output = fallback
        plan = ResponsePlan.from_model_output(output)
        if plan.speech or not fallback:
            return plan
        return ResponsePlan.from_model_output(fallback)

    async def _send_proactive(self, p: dict) -> None:
        user_id = p.get("user_id", "")
        name = self.persona.name_for(user_id) or p.get("display_name") or p.get("name", "朋友")
        reason = str(p.get("reason", "想自然地关心近况"))
        if not user_id:
            return
        session_key = f"proactive-private:{user_id}"
        cooldown = int(self._proactive_config.get("private_cooldown_sec", 43200))
        if not self.sessions.can_initiate(session_key, cooldown):
            return
        context = PromptContext(
            scene="proactive-private",
            user_input=f"现在主动给朋友{name}发一条私聊消息。",
            relationship_summary=f"联系人：{name}。本次联系动机：{reason}。",
            scene_state="这是主动联系，只能在工作作息内执行；一两句话即可。",
        )
        text = (await self._generate_plan(context)).text
        if not text:
            return
        account_id = str(p.get("account_id") or self.primary_social_account_id)
        await self.bus.publish_json(
            "social.send.request",
            {"ai_id": self.ai_id, "account_id": account_id, "channel": "qq", "chat": {"chat_id": user_id, "chat_type": "private", "chat_name": name}, "type": "text", "text": text},
        )
        self.sessions.mark_spoke(session_key)
        logger.info("[ai-agent:%s] 主动私聊 %s: %s", self.ai_id, name, text[:30])

    async def _join_group_checker(self, chat_id: str, explicitly_addressed: bool = False) -> bool:
        if not explicitly_addressed and (
            not self._proactive_enabled or not self.proactive.in_work_hours()
        ):
            logger.info("[ai-agent:%s] 群聊跳过: 非工作时段/未启用", self.ai_id)
            return False
        session = self.group_manager.session(chat_id)
        ready = self.group_manager.ready_to_join(
            chat_id,
            int(self._proactive_config.get("group_join_min_messages", 2)),
        )
        logger.info(
            "[ai-agent:%s] 群聊判断: active=%s ready=%s recent=%d",
            self.ai_id, session.active, ready, len(session.recent_messages),
        )
        if not explicitly_addressed and not session.active and not ready:
            return False
        window = self.conversation.window("group", chat_id)
        recent = list(window)[-5:]
        if not recent:
            logger.info("[ai-agent:%s] 群聊跳过: 会话窗口空", self.ai_id)
            return False
        relationship = await self._group_relationship(chat_id)
        score = self._group_participation_score(relationship)
        logger.info("[ai-agent:%s] 群聊判断: score=%.3f 门槛=%.2f", self.ai_id, score, float(self._proactive_config.get("group_min_score", 0.2)))
        if not explicitly_addressed and score < float(self._proactive_config.get("group_min_score", 0.2)):
            return False
        if explicitly_addressed:
            session_state = "对方在当前消息中明确 @ 了你"
        else:
            session_state = "已经在这个群的当前聊天中" if session.active else "尚未加入当前群聊会话"
        context = PromptContext(
            scene="group-join",
            user_input=(
                "对方明确 @ 了你。判断这条消息此刻是否适合回应。"
                if explicitly_addressed
                else "判断此刻是否适合参与群聊。"
            ),
            recent_messages=tuple(f"{role}: {content}" for role, content in recent),
            relationship_summary=(
                f"群关系：熟悉度 {float(relationship.get('familiarity', 0.0)):.2f}，"
                f"归属感 {float(relationship.get('belonging', 0.0)):.2f}，"
                f"好感 {float(relationship.get('affinity', 0.0)):.2f}，"
                f"活动意愿 {float(relationship.get('activity_willingness', 0.0)):.2f}；"
                f"综合参与度 {score:.2f}。当前状态：{session_state}。"
            ),
            scene_state=(
                (
                    "明确 @ 已绕过潜水、关系门槛、普通冷却和主动作息限制，但不代表必须发送。"
                    "结合消息与上下文判断是否确实适合接话；适合则 participate=true，不适合则 false。"
                )
                if explicitly_addressed
                else (
                    "像真人一样判断：未加入时，对话已形成且有自然切入点就加入，不必刻意等待；"
                    "已加入时，对能回应、能推进话题或与你有关的消息积极回复。"
                    "融入群聊比保持沉默更重要，只要不刷屏即可。"
                )
            ),
            output_protocol='只输出 JSON 对象：{"participate": true, "reason": "简短原因"}。',
        )
        try:
            messages = [
                ChatMessage(role="system", content=self.prompt_assembler.build_system_prompt(context)),
                ChatMessage(role="user", content=self.prompt_assembler.build_user_prompt(context)),
            ]
            raw = await self.agent_loop.run(messages)
            start, end = raw.find("{"), raw.rfind("}")
            decision = json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
            return decision.get("participate") is True
        except Exception as e:
            logger.warning("[ai-agent:%s] 群聊判断失败: %s", self.ai_id, e)
            return False

    async def _compensation_loop(self) -> None:
        interval = int(self.gcfg.get("social", "compensate_interval_sec", 600))
        while True:
            await asyncio.sleep(interval)
            try:
                for chat_key, window in self.conversation.all_windows():
                    if not chat_key.startswith("private:"):
                        continue
                    if window and window[-1][0] == "user":
                        await self._compensate(chat_key, window)
            except Exception as e:
                logger.warning("[ai-agent:%s] 补偿检查失败: %s", self.ai_id, e)

    async def _compensate(self, chat_key: str, window) -> None:
        chat_id = chat_key.split(":", 1)[1]
        recent = "\n".join(f"{role}: {content}" for role, content in list(window)[-6:])
        context = PromptContext(
            scene="social-compensation",
            user_input="请补回最后一条尚未回复的私聊消息。",
            recent_messages=(recent,),
            scene_state="这是被动私聊补偿，24 小时均应回复，不受主动联系作息限制。",
        )
        reply = (await self._generate_plan(context, "嗯嗯，我在听～")).text
        await self.bus.publish_json(
            "social.send.request",
            {"ai_id": self.ai_id, "account_id": self.primary_social_account_id, "channel": "qq", "chat": {"chat_id": chat_id, "chat_type": "private"}, "type": "text", "text": reply},
        )
        self.conversation.add_ai("private", chat_id, reply)
        logger.info("[ai-agent:%s] 补偿回复 %s: %s", self.ai_id, chat_id, reply[:30])

    async def _on_comment_request(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        feed_text = req.get("feed_text", "")
        author_name = req.get("author_name", "朋友")
        context = PromptContext(
            scene="qzone-comment",
            user_input=f"朋友{author_name}发了一条 QQ 空间动态：{feed_text}",
            relationship_summary=f"动态作者：{author_name}",
            scene_state="写一条一两句话、针对内容且像真人朋友的评论，不要官方客套。",
        )
        plan = await self._generate_plan(context)
        return json.dumps({"comment": self._limit_sentences(plan.text, 2)}, ensure_ascii=False).encode()

    async def tts_synthesize(self, text: str) -> dict | None:
        try:
            resp = await self.bus.request_json(
                "tts.synthesize.request",
                {"ai_id": self.ai_id, "text": text},
                timeout=30.0,
            )
            if resp.get("ok"):
                return {"audio_path": resp["audio_path"], "duration_sec": resp.get("duration_sec", 3)}
        except Exception as e:
            logger.warning("[ai-agent:%s] 语音合成失败: %s", self.ai_id, e)
        return None
