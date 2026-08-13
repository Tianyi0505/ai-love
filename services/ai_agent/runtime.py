
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
from services.ai_agent.llm.providers import anthropic_gw, deepseek, ollama
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
    def __init__(self, host, definition: AgentDefinition, account_ids: tuple[str, ...]) -> None:
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
        self._timeouts = self.gcfg.section("timeouts")
        self._fallbacks = self.gcfg.section("fallbacks")
        self.persona = Persona.from_definition(self.definition, self.gcfg)
        llm_config = self.gcfg.section("llm")
        self._llm = create_llm(self.persona.llm_models, llm_config)

        self.conversation = ConversationContext(
            window_size=int(self.gcfg.get("social", "window_size")),
            data_dir=f"/app/data/agents/{self.ai_id}",
            search_config=self.gcfg.section("search"),
        )

        image_config = self.gcfg.section("image")
        image_options = {
            key: value for key, value in image_config.items() if key != "describer"
        }
        self.prompt_assembler = PromptAssembler(self.definition)
        self.understanding = MessageUnderstanding(
            self.prompt_assembler,
            self._fallbacks,
            asr=None,
            image_describer=create_describer(
                image_config["describer"],
                **image_options,
            ),
        )

        self.agent_loop = AgentLoop(
            self._llm,
            self.prompt_assembler,
            ai_id=self.ai_id,
            max_rounds=int(llm_config["max_tool_rounds"]),
        )

        await register_tools(self.agent_loop, self.bus, self.ai_id, self._timeouts)

        self.memory = MemoryManager(
            self.bus, self._llm, self.ai_id, self.gcfg, self.prompt_assembler
        )

        self.retrieval = Retrieval(self)

        self.handlers = EventHandlers(self)

        self.join_checker = self._join_group_checker
        self.sessions = SessionManager(data_dir=f"/app/data/agents/{self.ai_id}")

        self.spawn(self._compensation_loop())

        self._proactive_config = dict(self.definition.behavior_policy["proactive"])
        self._proactive_enabled = self._proactive_config["enabled"]
        self.group_manager = GroupChatManager()
        self.proactive = ProactiveChat(self.definition.behavior_policy, self._fallbacks)
        if self._account_ids and self._proactive_enabled:
            self.spawn(self.proactive.loop(
                self,
                int(self._proactive_config["private_interval_sec"]),
                float(self._proactive_config["min_weight"]),
            ))
        self.spawn(self.memory.consolidate_loop(self.conversation.all_windows))

    @property
    def primary_social_account_id(self) -> str:
        return self._account_ids[0] if self._account_ids else ""

    async def drain(self) -> None:
        while self._in_flight:
            await asyncio.sleep(float(self.gcfg.get("social", "drain_poll_interval_sec")))

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
            resp = await self.bus.request_json(
                "relationship.list.request",
                {"ai_id": self.ai_id},
                timeout=float(self._timeouts["relationship_list_sec"]),
            )
            return resp.get("relationships", [])
        except Exception:
            return []

    async def list_personas(self) -> list[dict]:
        return await self._list_personas()

    async def send_private(self, p: dict) -> None:
        await self._send_proactive(p)

    def _can_speak_in_group(self, chat_id: str, cooldown_sec: int) -> bool:
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
            join_window_sec=int(self._proactive_config["group_join_window_sec"]),
            idle_sec=int(self._proactive_config["group_session_idle_sec"]),
            max_active_sec=int(self._proactive_config["group_session_max_sec"]),
            rest_sec=int(self._proactive_config["group_session_rest_sec"]),
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
        if started_at is not None and now - started_at < float(
            self._proactive_config["group_turn_in_flight_sec"]
        ):
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
                timeout=float(self._timeouts["relationship_group_sec"]),
            )
            return dict(response.get("relationship", {}))
        except Exception as exc:
            logger.warning("[ai-agent:%s] 读取群关系失败: %s", self.ai_id, exc)
            return {}

    def _group_participation_score(self, relationship: dict) -> float:
        weights = self._proactive_config["group_participation_weights"]
        score = (
            float(relationship.get("activity_willingness", 0.0)) * float(weights["activity_willingness"])
            + float(relationship.get("belonging", 0.0)) * float(weights["belonging"])
            + float(relationship.get("affinity", 0.0)) * float(weights["affinity"])
            + float(relationship.get("familiarity", 0.0)) * float(weights["familiarity"])
        )
        return max(0.0, min(1.0, score))

    def _group_cooldown(self, participation_score: float) -> int:
        minimum = int(self._proactive_config["group_min_cooldown_sec"])
        maximum = int(self._proactive_config["group_max_cooldown_sec"])
        exponent = float(self._proactive_config["group_cooldown_curve_exponent"])
        return round(minimum + (maximum - minimum) * (1.0 - participation_score) ** exponent)

    def _limit_sentences(self, text: str, max_sentences: int) -> str:
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
        reason = str(p.get("reason", self._fallbacks["proactive_unspecified_reason"]))
        if not user_id:
            return
        session_key = f"proactive-private:{user_id}"
        cooldown = int(self._proactive_config["private_cooldown_sec"])
        if not self.sessions.can_initiate(session_key, cooldown):
            return
        context = PromptContext(
            scene="proactive-private",
            user_input=self.prompt_assembler.render("proactive-private-input", name=name),
            relationship_summary=self.prompt_assembler.render(
                "proactive-private-relationship", name=name, reason=reason
            ),
            scene_state=self.prompt_assembler.template("proactive-private-state"),
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
            int(self._proactive_config["group_join_min_messages"]),
        )
        logger.info(
            "[ai-agent:%s] 群聊判断: active=%s ready=%s recent=%d",
            self.ai_id, session.active, ready, len(session.recent_messages),
        )
        if not explicitly_addressed and not session.active and not ready:
            return False
        window = self.conversation.window("group", chat_id)
        recent = list(window)[-int(self._proactive_config["group_join_history_messages"]):]
        if not recent:
            logger.info("[ai-agent:%s] 群聊跳过: 会话窗口空", self.ai_id)
            return False
        relationship = await self._group_relationship(chat_id)
        score = self._group_participation_score(relationship)
        logger.info("[ai-agent:%s] 群聊判断: score=%.3f 门槛=%.2f", self.ai_id, score, float(self._proactive_config["group_min_score"]))
        if not explicitly_addressed and score < float(self._proactive_config["group_min_score"]):
            return False
        if explicitly_addressed:
            session_state = self.prompt_assembler.template("group-join-session-addressed")
        else:
            session_state = self.prompt_assembler.template(
                "group-join-session-active" if session.active else "group-join-session-inactive"
            )
        context = PromptContext(
            scene="group-join",
            user_input=self.prompt_assembler.template(
                "group-join-addressed-input"
                if explicitly_addressed
                else "group-join-input"
            ),
            recent_messages=tuple(f"{role}: {content}" for role, content in recent),
            relationship_summary=self.prompt_assembler.render(
                "group-join-relationship",
                familiarity=f"{float(relationship.get('familiarity', 0.0)):.2f}",
                belonging=f"{float(relationship.get('belonging', 0.0)):.2f}",
                affinity=f"{float(relationship.get('affinity', 0.0)):.2f}",
                activity_willingness=f"{float(relationship.get('activity_willingness', 0.0)):.2f}",
                score=f"{score:.2f}",
                session_state=session_state,
            ),
            scene_state=self.prompt_assembler.template(
                "group-join-addressed-state"
                if explicitly_addressed
                else "group-join-state"
            ),
            output_protocol=self.prompt_assembler.template("participation-output"),
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
        interval = int(self.gcfg.get("social", "compensate_interval_sec"))
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
        history_limit = int(self.gcfg.get("social", "compensation_history_messages"))
        recent = "\n".join(f"{role}: {content}" for role, content in list(window)[-history_limit:])
        context = PromptContext(
            scene="social-compensation",
            user_input=self.prompt_assembler.template("social-compensation-input"),
            recent_messages=(recent,),
            scene_state=self.prompt_assembler.template("social-compensation-state"),
        )
        reply = (await self._generate_plan(context, self._fallbacks["response"])).text
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
            user_input=self.prompt_assembler.render(
                "qzone-comment-input", author_name=author_name, feed_text=feed_text
            ),
            relationship_summary=self.prompt_assembler.render(
                "qzone-comment-relationship", author_name=author_name
            ),
            scene_state=self.prompt_assembler.template("qzone-comment-state"),
        )
        plan = await self._generate_plan(context)
        return json.dumps(
            {
                "comment": self._limit_sentences(
                    plan.text,
                    int(self.gcfg.get("qq", "qzone_comment_max_sentences")),
                )
            },
            ensure_ascii=False,
        ).encode()

    async def tts_synthesize(self, text: str) -> dict | None:
        try:
            resp = await self.bus.request_json(
                "tts.synthesize.request",
                {"ai_id": self.ai_id, "text": text},
                timeout=float(self._timeouts["tts_request_sec"]),
            )
            if resp.get("ok"):
                return {"audio_path": resp["audio_path"], "duration_sec": resp["duration_sec"]}
        except Exception as e:
            logger.warning("[ai-agent:%s] 语音合成失败: %s", self.ai_id, e)
        return None
