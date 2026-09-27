"""私聊测试使用的隔离数据库；不读取生产数据库配置。"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@asynccontextmanager
async def isolated_database(url: str):
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or not (parsed.database or "").endswith("_test"):
        raise ValueError("必须使用本机独立的 *_test 数据库")
    schema = "private_reply_" + uuid4().hex
    admin = create_async_engine(parsed.set(drivername="postgresql+asyncpg"))
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        parsed.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
    )
    database = SimpleNamespace(engine=engine, session=async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield database
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def private_event(message_id=101, user_id=20000, segments=None):
    return {
        "post_type": "message", "message_type": "private", "sub_type": "friend",
        "self_id": 10000, "user_id": user_id, "message_id": message_id,
        "time": 1789000000, "message": segments or [{"type": "text", "data": {"text": "你好"}}],
        "sender": {"user_id": user_id, "nickname": "测试联系人"},
    }


class LocalBus:
    """只在进程内分派；没有任何外部连接回退。"""
    def __init__(self):
        self.handlers = {}
        self.published = []
        self.drop_wakeup = False

    async def publish_model(self, subject, message):
        self.published.append((subject, message))
        if not self.drop_wakeup and subject in self.handlers:
            await self.handlers[subject](message)

    async def request_model(self, subject, request, response_type, timeout):
        return await self.handlers[subject](request)


def recording_http(requests):
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "ok", "data": {"message_id": len(requests)}})
    return httpx.AsyncClient(transport=httpx.MockTransport(respond))

async def build_flow(db):
    import asyncio
    from pathlib import Path
    from unittest.mock import AsyncMock

    import yaml

    from agent.conversation.conversation_context import ConversationContext
    from agent.conversation.multimodal_input import MessageInput
    from agent.conversation.prompt_assembler import PromptAssembler
    from agent.conversation.response_plan import Emotion, ResponsePlan, Speech
    from agent.persona import Persona
    from agent.social.private_reply_service import PrivateReplyService
    from gateway.gateway_message_handler import GatewayMessageHandler
    from gateway.qq_channel import QQChannel
    from gateway.social_send_handler import SocialSendHandler
    from shared.agent_definition_store import AgentDefinitionStore
    from shared.contracts.rpc.memory import MemoryContextResponse
    from shared.contracts.rpc.relationship import RelationshipSummaryResponse
    from shared.conversation_repository import ConversationRepository
    from shared.global_settings_store import GlobalSettingsStore
    from shared.identity_repository import IdentityRepository
    from shared.private_interaction_repository import PrivateInteractionRepository
    from shared.service_settings import PrivateReplySettings
    from shared.social_delivery_repository import SocialDeliveryRepository

    class Config:
        async def watch(self, key, callback):
            pass

        async def get(self, key):
            data = yaml.safe_load((Path(__file__).parents[1] / 'deploy/config' / (key + '.yaml')).read_text(encoding='utf-8'))
            if key == 'ailove.config':
                data['qq']['whitelist'] = [str(value) for value in range(20000,20010)]
            return data

    definition = await AgentDefinitionStore(Config()).load('ai_luoyu')
    settings = await GlobalSettingsStore(Config()).load()
    bus = LocalBus()
    calls = []
    client = recording_http(calls)
    channel = QQChannel(dict(ws_url='ws://local.invalid', http_url='http://local.invalid',
        uin='10000', account_id='qq-main', message_timeout_sec=1, forward_timeout_sec=1,
        content_strategies=('quote','forward','voice','image','file','at','text')), client)
    jobs = PrivateInteractionRepository(db)
    deliveries = SocialDeliveryRepository(db)
    conversations = ConversationRepository(db, 180)
    owner = SimpleNamespace(owner_for=AsyncMock(return_value=definition.ai_id),
        route=AsyncMock(return_value=SimpleNamespace(ai_id=definition.ai_id)))
    sender = SocialSendHandler({'qq-main':channel}, conversations, deliveries, owner, send_retries=0)
    async def grounding(message, ai_id):
        return dict(current_sender=dict(person_id=message.meta['person_id'],display_name=message.sender.name),
                    references=[], recent_participants=[])
    handler = GatewayMessageHandler(channels={'qq-main':channel}, identities=IdentityRepository(db),
        conversations=conversations,router=owner,group_members=SimpleNamespace(),
        grounding=SimpleNamespace(ground_message=grounding),bus=bus,live_settings=SimpleNamespace(),
        priority_user_ids=frozenset(str(value) for value in range(20000,20010)),
        private_jobs=jobs,self_user_ids={'qq-main':'10000'})
    background = []
    def spawn(coro):
        task = asyncio.create_task(coro)
        background.append(task)
        return task
    runtime = SimpleNamespace(ai_id=definition.ai_id, definition=definition,settings=settings,bus=bus,
        persona=Persona.from_definition(definition, settings.social),prompt_assembler=PromptAssembler(definition),
        conversation=ConversationContext(window_size=20,timezone='Asia/Shanghai'),
        message_input=SimpleNamespace(build=AsyncMock(side_effect=lambda msg: MessageInput(msg.text or '[媒体消息]'))),
        memory=SimpleNamespace(search=AsyncMock(return_value=[]),context=AsyncMock(return_value=MemoryContextResponse(
            self_markdown='',person_markdown='',conversation_summary='')),activity=AsyncMock()),
        chat_agent=SimpleNamespace(generate_plan=AsyncMock(return_value=ResponsePlan(speech=[Speech(text='你好呀',delivery='text')],
            emotion=Emotion(name='neutral',intensity=.2),actions=[]))),
        _timeouts=settings.timeouts,spawn=spawn,stickers=SimpleNamespace(search=AsyncMock(return_value=None)),
        sticker_collector=SimpleNamespace(collect=AsyncMock()),tts=SimpleNamespace(synthesize=AsyncMock()),
        sticker_judge=SimpleNamespace(should_send=AsyncMock(return_value=False)))
    bus.handlers['relationship.chat.request'] = AsyncMock(return_value=RelationshipSummaryResponse(summary=''))
    bus.handlers['relationship.summary.request'] = AsyncMock(return_value=RelationshipSummaryResponse(summary=''))
    bus.handlers['social.send.request'] = sender.send
    bus.handlers['social.send.status.request'] = sender.status
    replies = PrivateReplyService(runtime,jobs,PrivateReplySettings())
    async def receive(message):
        await replies.handle(message.meta['private_reply_job_id'])
    bus.handlers['social.chat.'+definition.ai_id] = receive
    channel.set_message_handler(handler.handle)
    return SimpleNamespace(db=db, jobs=jobs,deliveries=deliveries,channel=channel,handler=handler,sender=sender,
        runtime=runtime,replies=replies,calls=calls,client=client,bus=bus,owner=owner,background=background)
