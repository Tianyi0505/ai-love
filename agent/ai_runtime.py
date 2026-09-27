from __future__ import annotations

import asyncio
import logging
import os

import httpx
from stevedore.driver import DriverManager
from stevedore.extension import error_on_conflict

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.conversation_context import ConversationContext
from agent.conversation.failover_chat_agent import FailoverChatAgent
from agent.conversation.message_understanding import MessageUnderstanding
from agent.conversation.multimodal_input import (
    DescribedMessageInputBuilder,
    DirectVisionMessageInputBuilder,
)
from agent.conversation.prompt_assembler import PromptAssembler
from agent.conversation.response_output_policy import ResponseOutputLimits, ResponseOutputPolicy
from agent.conversation.session_manager import SessionManager
from agent.conversation.social_message_input import SocialMessageInputBuilder
from agent.conversation.turn_coordinator import TurnCoordinator
from agent.extension_toolset_loader import load_toolset
from agent.live_event_handler import handle_live
from agent.memory_client import MemoryClient
from agent.persona import Persona
from agent.social.direct_vision_qzone_comment_generator import DirectVisionQZoneCommentGenerator
from agent.social.group_participation_service import GroupParticipationService
from agent.social.group_repeat_service import GroupRepeatJudge, GroupRepeatService
from agent.social.private_reply_service import PrivateReplyService
from agent.social.proactive_private_service import ProactivePrivateService
from agent.social.qzone_comment_generator import QZoneCommentGenerator
from agent.social.social_message_handler import handle_social
from agent.social.sticker_client import StickerClient
from agent.social.sticker_collector import StickerCollector
from agent.social.sticker_judge import StickerJudge
from agent.vision.image_describer import ImageDescriber
from agent.vision.image_fetcher import ImageFetcher
from agent.vision.vision_output_policy import VisionOutputLimits, VisionOutputPolicy
from shared.chat_model_factory import (
    create_chat_model,
    create_openai_compatible_chat_model,
)
from shared.contracts.agent import AgentDefinition
from shared.contracts.behavior import BehaviorSchedule
from shared.contracts.events import TurnRequest
from shared.contracts.rpc.social import CommentRequest, CommentResponse, SocialSendResponse
from shared.contracts.social import SocialMessage
from shared.contracts.turn import ResponseCommand
from shared.global_settings_store import GlobalSettingsStore
from shared.private_interaction_repository import PrivateInteractionRepository

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
        self._draining = False

    # 启动服务
    async def start(self) -> None:
        context = getattr(self._host, "plugin_context", None)
        model_factory = context.require("model.factory") if context else create_chat_model
        self.ai_id = self.definition.ai_id
        self.private_jobs = PrivateInteractionRepository(self._host._db)
        self.private_replies = PrivateReplyService(self, self.private_jobs, self._host._settings.private_reply)

        self.settings = await GlobalSettingsStore(self.cfg.nacos).load()
        self._timeouts = self.settings.timeouts
        self.persona = Persona.from_definition(self.definition, self.settings.social)
        llm_config = self.settings.llm

        self.conversation = ConversationContext(
            window_size=self.settings.social.window_size,
            timezone=self.definition.behavior_policy.proactive.timezone,
        )

        image_config = self.settings.image
        self.prompt_assembler = PromptAssembler(self.definition)
        self._vision_fetch_client = httpx.AsyncClient(
            timeout=image_config.fetch_timeout_sec,
            headers=image_config.fetch_headers,
            follow_redirects=True,
        )
        self.image_fetcher = ImageFetcher(self._vision_fetch_client, image_config.media_type)
        self._vision_model_http_client = httpx.AsyncClient(
            timeout=image_config.request_timeout_sec,
        )
        vision_model = create_openai_compatible_chat_model(
            image_config.model,
            api_key=os.environ[image_config.api_key_env],
            base_url=image_config.base_url,
            max_tokens=image_config.max_tokens,
            timeout_sec=image_config.request_timeout_sec,
            max_retries=image_config.retry_count,
            http_async_client=self._vision_model_http_client,
        )
        vision_output_policy = VisionOutputPolicy(VisionOutputLimits.model_validate(image_config.output_limits))
        self.vision = ImageDescriber(
            vision_model,
            f"openai-compatible:{image_config.model}",
            self.image_fetcher,
            vision_output_policy,
            image_config.prompt,
            image_config.max_tokens,
            image_config.retry_count,
            self.settings.observability,
        )
        self.understanding = MessageUnderstanding(
            self.prompt_assembler,
            {},
            self.vision,
        )
        multimodal_model_ids = self.definition.model_profile.multimodal_model_ids
        private_message_input = (
            DirectVisionMessageInputBuilder(self.prompt_assembler, {}, self.image_fetcher)
            if multimodal_model_ids
            else DescribedMessageInputBuilder(self.understanding)
        )
        self.message_input = SocialMessageInputBuilder(
            private_message_input,
            self.conversation,
            self.image_fetcher,
            self.vision,
            direct_vision=bool(multimodal_model_ids),
        )

        response_output_policy = ResponseOutputPolicy(ResponseOutputLimits.model_validate(llm_config.output_limits))
        toolset = await load_toolset(
            self.bus,
            self.ai_id,
            self._timeouts,
        )

        async def current_tools():
            return await load_toolset(self.bus, self.ai_id, self._timeouts)

        def build_chat_agent(model_id: str) -> ChatAgent:
            model = model_factory(
                model_id,
                models=llm_config.models,
                max_tokens=llm_config.max_tokens,
                timeout_sec=llm_config.provider_request_timeout_sec,
                max_retries=llm_config.retry_count,
            )
            return ChatAgent(
                model=model,
                model_name=model_id,
                tools=toolset,
                output_policy=response_output_policy,
                max_requests=llm_config.max_requests,
                participation_max_requests=llm_config.participation_max_requests,
                max_tokens=llm_config.max_tokens,
                retry_count=llm_config.retry_count,
                tool_retry_count=llm_config.tool_retry_count,
                observability=self.settings.observability,
                tool_loader=current_tools if context else None,
            )

        fallback_model_id = self.definition.model_profile.model_id
        fallback_agent = build_chat_agent(fallback_model_id)
        if multimodal_model_ids:
            primary_agents = tuple(
                (model_id, build_chat_agent(model_id))
                for model_id in multimodal_model_ids
            )
            self.chat_agent = FailoverChatAgent(
                primaries=primary_agents,
                fallback=fallback_agent,
                image_describer=self.vision,
                fallback_model_name=fallback_model_id,
            )
        else:
            self.chat_agent = fallback_agent

        self.stickers = StickerClient(self.bus, self.ai_id, self._timeouts)
        self.sticker_judge = StickerJudge(
            vision_model,
            f"openai-compatible:{image_config.model}",
            self.image_fetcher,
            self.prompt_assembler.template("sticker-selection"),
            image_config.max_tokens,
            image_config.retry_count,
            self.settings.observability,
        )
        tts_config = self.settings.tts
        self._tts_http_client = httpx.AsyncClient(timeout=self._timeouts.tts_request_sec)
        tts_arguments = {
            "ai_id": self.ai_id,
            "base_url": tts_config.base_url,
            "http_client": self._tts_http_client,
        }
        self.tts = context.require("speech.clients").create(tts_config.provider, **tts_arguments) if context else DriverManager(
            namespace="ai_love.tts",
            name=tts_config.provider,
            invoke_on_load=True,
            invoke_kwds=tts_arguments,
            conflict_resolver=error_on_conflict,
        ).driver

        self.coordinator = TurnCoordinator()

        self.memory = MemoryClient(
            self.bus,
            self.ai_id,
            self.settings.memory,
            self._timeouts,
        )
        self.sessions = SessionManager(
            self._host.redis,
            self.ai_id,
            self.settings.social.session_state_ttl_sec,
        )
        self.group_repeat = GroupRepeatService(
            self._host.redis,
            self.ai_id,
            self.settings.social.session_state_ttl_sec,
        )
        group_repeat_model_id = (
            self.definition.model_profile.group_repeat_model_id
            or self.definition.model_profile.model_id
        )
        group_repeat_max_tokens = min(llm_config.max_tokens, 256)
        self.group_repeat_judge = GroupRepeatJudge(
            model=model_factory(
                group_repeat_model_id,
                models=llm_config.models,
                max_tokens=group_repeat_max_tokens,
                timeout_sec=llm_config.provider_request_timeout_sec,
                max_retries=llm_config.retry_count,
            ),
            model_name=group_repeat_model_id,
            conversation=self.conversation,
            prompt_assembler=self.prompt_assembler,
            ai_name=self.persona.name,
            history_limit=self.settings.social.prompt_history_messages,
            max_attempts=min(llm_config.participation_max_requests, llm_config.retry_count + 1),
            max_tokens=group_repeat_max_tokens,
            observability=self.settings.observability,
        )
        behavior_schedule = BehaviorSchedule.from_config(self.definition.behavior_policy)
        self.group_participation = GroupParticipationService(
            ai_id=self.ai_id,
            account_id=self.primary_social_account_id,
            bus=self.bus,
            relationship_timeout_sec=self._timeouts.relationship_group_sec,
            sessions=self.sessions,
            conversation=self.conversation,
            persona=self.persona,
            prompt_assembler=self.prompt_assembler,
            chat_agent=self.chat_agent,
            proactive=self.definition.behavior_policy.proactive,
            behavior_schedule=behavior_schedule,
            group_whitelist=self.definition.relationship_policy.group_ceiling_whitelist,
        )
        self.proactive_private = ProactivePrivateService(
            ai_id=self.ai_id,
            default_account_id=self.primary_social_account_id,
            bus=self.bus,
            relationship_timeout_sec=self._timeouts.relationship_group_sec,
            interactions=self.private_jobs,
            allowed_account_ids=self._account_ids,
            conversation=self.conversation,
            memory=self.memory,
            persona=self.persona,
            prompt_assembler=self.prompt_assembler,
            chat_agent=self.chat_agent,
            proactive=self.definition.behavior_policy.proactive,
            behavior_schedule=behavior_schedule,
            send_response=self.send_response,
        )
        if self.definition.behavior_policy.proactive.enabled:
            self.spawn(self.proactive_private.loop())
        self.comment_generator = (
            DirectVisionQZoneCommentGenerator(
                self.settings.qq,
                self.prompt_assembler,
                self.chat_agent,
                self.image_fetcher,
            )
            if multimodal_model_ids
            else QZoneCommentGenerator(
                self.settings.qq,
                self.prompt_assembler,
                self.chat_agent,
                self.vision,
            )
        )
        self.sticker_collector = StickerCollector(
            self.ai_id,
            self.vision,
            self.stickers,
            self.settings.sticker.collect_min_quality,
        )
        self.spawn(self.private_replies.loop())

    # 返回主社交账号标识
    @property
    def primary_social_account_id(self) -> str:
        return self._account_ids[0]

    # 等待在途任务完成
    async def drain(self) -> None:
        self._draining = True
        proactive = getattr(self, "proactive_private", None)
        if proactive is not None:
            proactive.stop_requested = True
        while self._in_flight or (proactive is not None and proactive.active):
            await asyncio.sleep(self.settings.social.drain_poll_interval_sec)

    # 停止服务
    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        for name in ("_vision_fetch_client", "_vision_model_http_client", "_tts_http_client"):
            client = getattr(self, name, None)
            if client is not None:
                await client.aclose()

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
    async def handle_social(self, message: SocialMessage) -> None:
        if self._draining:
            raise RuntimeError("智能体正在排空")
        if message.chat.chat_type.value == "private":
            if not message.meta.get("private_reply_job_id"):
                logger.error("私聊消息缺少持久任务: message_id=%s", message.message_id)
                return
            self.spawn(self.private_replies.handle(message.meta["private_reply_job_id"]))
            return
        key = f"{self.ai_id}\x1f{str(message.meta.get('conversation_id') or '') or message.chat.chat_id}"
        self._in_flight += 1

        # 同一会话串行演进，不同会话并发
        async def guarded() -> None:
            try:
                async with self.coordinator.lock_for(key):
                    await handle_social(self, message)
                    await self.memory.activity(
                        person_id=str(message.meta.get("person_id") or ""),
                        conversation_id=str(message.meta.get("conversation_id") or ""),
                        message_id=str(message.message_id or ""),
                    )
            finally:
                self._in_flight -= 1

        self.spawn(guarded())

    # 处理直播
    async def handle_live(self, event) -> None:
        self._in_flight += 1
        try:
            await handle_live(self, event)
        finally:
            self._in_flight -= 1

    # 处理轮次
    async def handle_turn(self, turn: TurnRequest):
        social_message = turn.metadata.get("social_message")
        if social_message:
            await self.handle_social(SocialMessage.model_validate(social_message))
            return None
        raise ValueError(f"暂不支持的回合来源: {turn.source}")

    # 处理评论
    async def handle_comment(self, request: CommentRequest) -> CommentResponse:
        self._in_flight += 1
        try:
            return await self.comment_generator.generate(request)
        finally:
            self._in_flight -= 1

    # 统一发送回复指令
    async def send_response(self, command: ResponseCommand) -> SocialSendResponse:
        return await self.bus.request_model(
            "social.send.request",
            command.send_request(),
            SocialSendResponse,
            timeout=self.settings.social.send_timeout_sec,
        )
