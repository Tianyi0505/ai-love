
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from string import Template

from agent.generation.agent_loop import AgentLoop
from agent.clients.extensions import register_tools
from agent.clients.memory import MemoryClient
from agent.clients.sticker import StickerClient
from agent.clients.tts import TTSClient
from agent.context.conversation import ConversationContext
from agent.application.proactive import GroupChatManager, ProactiveChat
from agent.context.speaking_state import SessionManager
from agent.application.live import handle_live
from agent.application.social import handle_social
from agent.application.turn_coordinator import TurnCoordinator
from shared.contracts.turn import AgentExecutionContext, ResponseCommand, new_run_id
from shared.infrastructure.run_repo import AgentRunRepository
from ai.llm.providers import anthropic_gw, deepseek, ollama
from ai.llm.factory import create_llm
from ai.llm.types import ChatMessage
from agent.context.understanding import MessageUnderstanding
from agent.persona.model import Persona
from agent.generation.prompting import PromptAssembler, PromptContext
from shared.contracts.agent import AgentDefinition
from shared.contracts.events import TurnRequest
from shared.contracts.social import SocialMessage
from agent.generation.response import ResponsePlan
from shared.infrastructure.global_config import GlobalConfig
from ai.vision.factory import create_vision

logger = logging.getLogger("ailove.ai-agent")


# 运行单个智能体实例
class AIRuntime:
    # 初始化当前实例
    def __init__(self, host, definition: AgentDefinition, account_ids: tuple[str, ...]) -> None:
        self._host = host
        self.definition = definition
        self.cfg = host.cfg
        self.bus = host.bus
        self._account_ids = account_ids
        self._tasks: list[asyncio.Task] = []
        self._in_flight = 0
        self._group_turns_in_flight: dict[str, float] = {}

    # 启动服务
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
            key: value for key, value in image_config.items() if key != "provider"
        }
        self.prompt_assembler = PromptAssembler(self.definition)
        self.vision = create_vision(
            image_config["provider"],
            **image_options,
        )
        self.understanding = MessageUnderstanding(
            self.prompt_assembler,
            self._fallbacks,
            asr=None,
            image_describer=self.vision,
        )

        self.agent_loop = AgentLoop(
            self._llm,
            self.prompt_assembler,
            ai_id=self.ai_id,
            max_rounds=int(llm_config["max_tool_rounds"]),
        )

        await register_tools(self.agent_loop, self.bus, self.ai_id, self._timeouts)

        self.stickers = StickerClient(self.bus, self.ai_id, self._timeouts)
        self.tts = TTSClient(self.bus, self.ai_id, self._timeouts)

        self.coordinator = TurnCoordinator()
        self.run_repo = (
            AgentRunRepository(getattr(self._host, "_db", None))
            if getattr(self._host, "_db", None) is not None
            else None
        )

        self.memory = MemoryClient(
            self.bus,
            self.ai_id,
            self.gcfg.section("memory"),
            self._timeouts,
        )
        self.join_checker = self._join_group_checker
        self.sessions = SessionManager(data_dir=f"/app/data/agents/{self.ai_id}")

        self.spawn(self._compensation_loop())

        self._proactive_config = dict(self.definition.behavior_policy["proactive"])
        self._proactive_enabled = self._proactive_config["enabled"]
        self.group_manager = GroupChatManager()
        self.proactive = ProactiveChat(self.definition.behavior_policy)
        if self._account_ids and self._proactive_enabled:
            self.spawn(self.proactive.loop(
                self,
                int(self._proactive_config["private_interval_sec"]),
                float(self._proactive_config["min_weight"]),
            ))

    # 返回主社交账号标识
    @property
    def primary_social_account_id(self) -> str:
        return self._account_ids[0] if self._account_ids else ""

    # 等待在途任务完成
    async def drain(self) -> None:
        while self._in_flight:
            await asyncio.sleep(float(self.gcfg.get("social", "drain_poll_interval_sec")))

    # 停止服务
    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    # 创建后台任务
    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        task.add_done_callback(self._discard_task)
        return task

    # 清理已结束的后台任务
    def _discard_task(self, task: asyncio.Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("[ai-agent:%s] 后台任务失败: %s", self.ai_id, task.exception())

    # 处理社交
    async def handle_social(self, payload: bytes) -> None:
        message = SocialMessage.from_dict(json.loads(payload))
        key = (
            f"{self.ai_id}\x1f"
            f"{str(message.meta.get('conversation_id') or '') or message.chat.chat_id}"
        )
        self._in_flight += 1

        # 同一会话串行演进，不同会话并发
        async def guarded() -> None:
            try:
                async with self.coordinator.lock_for(key):
                    await handle_social(self, payload)
                    try:
                        await self.memory.activity(
                            person_id=str(message.meta.get("person_id") or ""),
                            conversation_id=str(message.meta.get("conversation_id") or ""),
                            message_id=str(message.message_id or ""),
                        )
                    except Exception as exc:
                        logger.warning("[ai-agent:%s] 发布记忆活动失败: %s", self.ai_id, exc)
            finally:
                self._in_flight -= 1

        self.spawn(guarded())

    # 处理直播
    async def handle_live(self, payload: bytes) -> None:
        self._in_flight += 1
        try:
            await handle_live(self, payload)
        finally:
            self._in_flight -= 1

    # 处理轮次
    async def handle_turn(self, turn: TurnRequest):
        social_message = turn.metadata.get("social_message")
        if social_message:
            await self.handle_social(json.dumps(social_message, ensure_ascii=False).encode("utf-8"))
            return None
        raise ValueError(f"暂不支持的回合来源: {turn.source}")

    # 处理评论
    async def handle_comment(self, payload: bytes) -> bytes:
        self._in_flight += 1
        try:
            return await self._on_comment_request(payload)
        finally:
            self._in_flight -= 1

    # 列出人格列表
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

    # 列出人格列表
    async def list_personas(self) -> list[dict]:
        return await self._list_personas()

    # 发送私聊
    async def send_private(self, p: dict) -> None:
        await self._send_proactive(p)

    # 判断是否可以在群聊发言
    def _can_speak_in_group(self, chat_id: str, cooldown_sec: int) -> bool:
        chat_key = f"group:{chat_id}"
        if cooldown_sec > 0:
            return self.sessions.can_initiate(chat_key, cooldown_sec)
        return self.sessions.can_speak(chat_key)

    # 标记群聊已发言状态
    def _mark_group_spoke(self, chat_id: str) -> None:
        self.sessions.mark_spoke(f"group:{chat_id}")

    # 标记群聊已回复状态
    def _mark_group_replied(self, chat_id: str) -> None:
        self.sessions.mark_replied(f"group:{chat_id}")

    # 记录群聊消息
    def _observe_group_message(self, chat_id: str) -> None:
        self.group_manager.observe(
            chat_id,
            join_window_sec=int(self._proactive_config["group_join_window_sec"]),
            idle_sec=int(self._proactive_config["group_session_idle_sec"]),
            max_active_sec=int(self._proactive_config["group_session_max_sec"]),
            rest_sec=int(self._proactive_config["group_session_rest_sec"]),
        )

    # 激活群聊会话
    def _activate_group_session(self, chat_id: str) -> None:
        self.group_manager.activate(chat_id)

    # 开始群聊回复轮次
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

    # 完成群聊轮次
    def _finish_group_turn(self, chat_id: str) -> None:
        self._group_turns_in_flight.pop(chat_id, None)

    # 加载群聊关系
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

    # 计算群聊参与度
    def _group_participation_score(self, relationship: dict) -> float:
        weights = self._proactive_config["group_participation_weights"]
        score = (
            float(relationship.get("activity_willingness", 0.0)) * float(weights["activity_willingness"])
            + float(relationship.get("belonging", 0.0)) * float(weights["belonging"])
            + float(relationship.get("affinity", 0.0)) * float(weights["affinity"])
            + float(relationship.get("familiarity", 0.0)) * float(weights["familiarity"])
        )
        return max(0.0, min(1.0, score))

    # 计算群聊发言冷却时间
    def _group_cooldown(self, participation_score: float) -> int:
        minimum = int(self._proactive_config["group_min_cooldown_sec"])
        maximum = int(self._proactive_config["group_max_cooldown_sec"])
        exponent = float(self._proactive_config["group_cooldown_curve_exponent"])
        return round(minimum + (maximum - minimum) * (1.0 - participation_score) ** exponent)

    # 限制回复句子数量
    def _limit_sentences(self, text: str, max_sentences: int) -> str:
        sentences = re.split(r"(?<=[。！？!?])", text.strip())
        if len(sentences) <= max_sentences:
            return text
        return "".join(sentences[:max_sentences])

    # 生成回复计划
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

    # 统一发送回复指令
    async def send_response(self, command: ResponseCommand) -> dict:
        try:
            return await self.bus.request_json(
                "social.send.request",
                command.send_payload(),
                timeout=float(self.gcfg.get("social", "send_timeout_sec")),
            )
        except Exception as exc:
            return {"ok": False, "fallback_note": str(exc) or "发送确认超时"}

    # 发送主动交互
    async def _send_proactive(self, p: dict) -> None:
        user_id = p.get("user_id", "")
        name = self.persona.name_for(user_id) or p.get("display_name") or p.get("name", "朋友")
        reason = str(p.get("reason") or "").strip()
        if not user_id or not reason:
            return
        session_key = f"proactive-private:{user_id}"
        cooldown = int(self._proactive_config["private_cooldown_sec"])
        if not self.sessions.can_initiate(session_key, cooldown):
            return
        memory_context = await self.memory.context(person_id=str(p.get("person_id") or ""))
        context = PromptContext(
            scene="proactive-private",
            user_input=self.prompt_assembler.render(
                "proactive-private-input", name=name, reason=reason
            ),
            relationship_summary=self.prompt_assembler.render(
                "proactive-private-relationship", name=name
            ),
            self_document=str(memory_context.get("self_markdown") or ""),
            person_document=str(memory_context.get("person_markdown") or ""),
        )
        account_id = str(p.get("account_id") or self.primary_social_account_id)
        run_id = new_run_id()
        execution = AgentExecutionContext(
            run_id=run_id,
            ai_id=self.ai_id,
            account_id=account_id,
            platform="qq",
            chat_type="private",
            chat_id=user_id,
            sender_person_id=str(p.get("person_id") or ""),
            sender_platform_user_id=user_id,
            source="proactive",
        )
        async with self.coordinator.lock_for(execution.conversation_key):
            if self.run_repo is not None:
                await self.run_repo.start_run(execution)
            text = (await self._generate_plan(context)).text
            if not text:
                if self.run_repo is not None:
                    await self.run_repo.finish_run(run_id, "empty_plan")
                return
            command = ResponseCommand(
                run_id=run_id,
                ai_id=self.ai_id,
                account_id=account_id,
                conversation_id=execution.conversation_id,
                platform="qq",
                chat={"chat_id": user_id, "chat_type": "private", "chat_name": name},
                text=text,
            )
            result = await self.send_response(command)
            if self.run_repo is not None:
                await self.run_repo.finish_run(
                    run_id,
                    "sent" if result.get("ok") else "send_failed",
                    response_text=text,
                )
            if not result.get("ok"):
                return
        self.sessions.mark_spoke(session_key)
        logger.info("[ai-agent:%s] 主动私聊 %s: %s", self.ai_id, name, text[:30])

    # 判断是否加入群聊对话
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
        current_role, current_message = recent[-1]
        history = recent[:-1]
        relationship = await self._group_relationship(chat_id)
        score = self._group_participation_score(relationship)
        logger.info("[ai-agent:%s] 群聊判断: score=%.3f 门槛=%.2f", self.ai_id, score, float(self._proactive_config["group_min_score"]))
        if not explicitly_addressed and score < float(self._proactive_config["group_min_score"]):
            return False
        session_state = self.prompt_assembler.template(
            "group-join-session-active" if session.active else "group-join-session-inactive"
        )
        context = PromptContext(
            scene="group-join",
            user_input=self.prompt_assembler.render(
                "group-join-addressed-input"
                if explicitly_addressed
                else "group-join-input",
                current_message=f"{current_role}: {current_message}",
            ),
            recent_messages=tuple(f"{role}: {content}" for role, content in history),
            relationship_summary=self.prompt_assembler.render(
                "group-join-relationship",
                familiarity=f"{float(relationship.get('familiarity', 0.0)):.2f}",
                belonging=f"{float(relationship.get('belonging', 0.0)):.2f}",
                affinity=f"{float(relationship.get('affinity', 0.0)):.2f}",
                activity_willingness=f"{float(relationship.get('activity_willingness', 0.0)):.2f}",
                score=f"{score:.2f}",
                session_state=session_state,
            ),
            output_protocol=self.prompt_assembler.template("participation-output"),
        )
        try:
            messages = [
                ChatMessage(role="system", content=self.prompt_assembler.build_system_prompt(context)),
                ChatMessage(role="user", content=self.prompt_assembler.build_user_prompt(context)),
            ]
            raw = await self.agent_loop.run(messages, allow_tools=False)
            start, end = raw.find("{"), raw.rfind("}")
            decision = json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
            return decision.get("participate") is True
        except Exception as e:
            logger.warning("[ai-agent:%s] 群聊判断失败: %s", self.ai_id, e)
            return False

    # 持续执行补偿回复循环
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

    # 执行群聊补偿回复
    async def _compensate(self, chat_key: str, window) -> None:
        chat_id = chat_key.split(":", 1)[1]
        history_limit = int(self.gcfg.get("social", "compensation_history_messages"))
        recent = list(window)[-history_limit:]
        _, current_message = recent[-1]
        context = PromptContext(
            scene="social-private",
            user_input=current_message,
            recent_messages=tuple(
                f"{role}: {content}" for role, content in recent[:-1]
            ),
        )
        run_id = new_run_id()
        execution = AgentExecutionContext(
            run_id=run_id,
            ai_id=self.ai_id,
            account_id=self.primary_social_account_id,
            platform="qq",
            chat_type="private",
            chat_id=chat_id,
            source="compensate",
        )
        async with self.coordinator.lock_for(execution.conversation_key):
            if self.run_repo is not None:
                await self.run_repo.start_run(execution)
            reply = (await self._generate_plan(context, self._fallbacks["response"])).text
            command = ResponseCommand(
                run_id=run_id,
                ai_id=self.ai_id,
                account_id=self.primary_social_account_id,
                conversation_id=execution.conversation_id,
                platform="qq",
                chat={"chat_id": chat_id, "chat_type": "private"},
                text=reply,
            )
            result = await self.send_response(command)
            if self.run_repo is not None:
                await self.run_repo.finish_run(
                    run_id,
                    "sent" if result.get("ok") else "send_failed",
                    response_text=reply,
                )
            if result.get("ok"):
                self.conversation.add_ai("private", chat_id, reply)
                logger.info("[ai-agent:%s] 补偿回复 %s: %s", self.ai_id, chat_id, reply[:30])

    # 处理评论请求
    async def _on_comment_request(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        feed_text = req.get("feed_text", "")
        author_name = req.get("author_name", "朋友")
        picture_urls = [str(url) for url in req.get("picture_urls", []) if str(url)]
        if picture_urls:
            descriptions = await asyncio.gather(
                *(self._describe_image(url) for url in picture_urls)
            )
            picture_text = "\n".join(
                Template(str(self.gcfg.get("qq", "qzone_picture_template"))).substitute(
                    index=index,
                    description=description,
                )
                for index, description in enumerate(descriptions, start=1)
            )
            feed_text = Template(str(self.gcfg.get("qq", "qzone_feed_template"))).substitute(
                content=feed_text,
                pictures=picture_text,
                comments="",
                reply="",
            ).strip()
        context = PromptContext(
            scene="qzone-comment",
            user_input=self.prompt_assembler.render(
                "qzone-comment-input", author_name=author_name, feed_text=feed_text
            ),
            relationship_summary=self.prompt_assembler.render(
                "qzone-comment-relationship", author_name=author_name
            ),
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

    # 描述图片
    async def _describe_image(self, image_url: str) -> str:
        try:
            result = await self.vision.describe(image_url)
            return str(result.description or self._fallbacks["image_unreadable"])
        except Exception as exc:
            logger.warning("[ai-agent:%s] 图片理解失败: %s", self.ai_id, exc)
            return str(self._fallbacks["image_unreadable"])

    # 收集表情列表
    async def collect_stickers(self, image_urls: list[str]) -> None:
        await asyncio.gather(*(self._collect_sticker(url) for url in image_urls))

    # 收集表情
    async def _collect_sticker(self, image_url: str) -> None:
        try:
            description = await self.vision.describe(image_url)
            min_quality = float(self.gcfg.get("sticker", "collect_min_quality"))
            if (
                description.match_quality < min_quality
                or not description.sticker_description
            ):
                return
            added = await self.stickers.add(
                image_url,
                description.sticker_description,
                description.tags,
                description.match_quality,
            )
            if added:
                logger.info("[ai-agent:%s] 收藏表情: %s", self.ai_id, description.description)
        except Exception as exc:
            logger.warning("[ai-agent:%s] 收藏表情失败: %s", self.ai_id, exc)
