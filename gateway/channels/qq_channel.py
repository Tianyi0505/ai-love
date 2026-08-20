from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import websockets
from pydantic import BaseModel, ConfigDict, TypeAdapter
from stevedore.named import NamedExtensionManager

from gateway.channels.channel import Channel, ChannelCapabilities
from gateway.channels.content_type_resolver import ContentContext, ContentTypeResolver
from gateway.channels.napcat_message_event import NapCatMessageEvent
from gateway.enums import Channel as ChannelEnum
from gateway.enums import EventPostType, SegmentType, SendAction
from shared.contracts.rpc.social import SocialSendRequest, SocialSendResponse
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender

logger = logging.getLogger("ailove.gateway.qq")


class QQChannelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ws_url: str
    http_url: str
    uin: str | int
    account_id: str
    message_timeout_sec: float
    forward_timeout_sec: float
    content_strategies: tuple[str, ...]


# 接入QQ消息收发渠道
class QQChannel(Channel):
    name = ChannelEnum.QQ.value

    # 初始化当前实例
    def __init__(self, cfg: dict, http_client: httpx.AsyncClient) -> None:
        super().__init__(cfg)
        settings = QQChannelSettings.model_validate(cfg)
        self._http_client = http_client
        self._ws_url = settings.ws_url
        self._http_url = settings.http_url
        self._self_uin = str(settings.uin)
        self.account_id = settings.account_id
        self._message_timeout_sec = settings.message_timeout_sec
        self._forward_timeout_sec = settings.forward_timeout_sec
        self._ws = None
        self._session_locks: dict[str, asyncio.Lock] = {}
        strategy_names = list(settings.content_strategies)
        strategies = NamedExtensionManager(
            namespace="ai_love.content_strategies",
            names=strategy_names,
            invoke_on_load=True,
        )
        self._content_resolver = ContentTypeResolver([extension.obj for extension in strategies.extensions])

    # 启动服务
    async def start(self) -> None:
        async with asyncio.TaskGroup() as tasks:
            async for ws in websockets.connect(self._ws_url):
                self._ws = ws
                try:
                    logger.info("[qq] 已连接 NapCat WS: %s", self._ws_url)
                    async for raw in ws:
                        payload = TypeAdapter(dict[str, Any]).validate_json(raw)
                        if payload["post_type"] == EventPostType.MESSAGE.value:
                            msg = self._to_message(NapCatMessageEvent.model_validate(payload))
                            if msg is not None:
                                tasks.create_task(self._handle_message(msg))
                finally:
                    self._ws = None

    # 停止服务
    async def stop(self) -> None:
        if self._ws is not None:
            await self._ws.close()

    # 按会话处理消息：不同会话并行，同一会话内串行
    async def _handle_message(self, msg: SocialMessage) -> None:
        key = f"{msg.account_id}:{msg.chat.chat_type.value}:{msg.chat.chat_id}"
        lock = self._session_locks.setdefault(key, asyncio.Lock())
        async with lock:
            await asyncio.wait_for(self.message_handler(msg), timeout=self._message_timeout_sec)

    # 转换为消息
    def _to_message(self, evt: NapCatMessageEvent) -> SocialMessage | None:
        segments = evt.message
        msg_type = evt.message_type
        user_id = str(evt.user_id)
        text = "".join(str(seg.data["text"]) for seg in segments if seg.type == SegmentType.TEXT.value).strip()
        at_targets = [str(seg.data["qq"]) for seg in segments if seg.type == SegmentType.AT.value]
        at_mentions = [
            {
                "user_id": str(seg.data["qq"]),
                "name": str(seg.data["name"]),
            }
            for seg in segments
            if seg.type == SegmentType.AT.value
        ]
        images = [seg.data for seg in segments if seg.type == SegmentType.IMAGE.value]
        voices = [seg.data for seg in segments if seg.type == SegmentType.RECORD.value]
        forwards = [seg.data for seg in segments if seg.type == SegmentType.FORWARD.value]
        files = [seg.data for seg in segments if seg.type == "file"]
        reply_id = ""
        quote_user_id = ""
        for seg in segments:
            if seg.type == SegmentType.REPLY.value:
                reply_id = str(seg.data["id"])
                quote_user_id = str(seg.data["user_id"])
                break
        if not text and not at_targets and not images and not voices and not forwards and not files and not reply_id:
            return None
        if msg_type == ChatType.PRIVATE.value:
            chat = ChatType.PRIVATE
            chat_id = user_id
            chat_name = evt.sender.nickname
        else:
            chat = ChatType.GROUP
            if evt.group_id is None:
                raise ValueError("NapCat 群消息缺少 group_id")
            chat_id = str(evt.group_id)
            chat_name = evt.group_name if evt.group_name is not None else ""
        meta: dict = {
            "at_user_ids": at_targets,
            "at_mentions": at_mentions,
            "sender_role": evt.sender.role if evt.sender.role is not None else "",
        }
        ctx = self._content_resolver.resolve(
            ContentContext(
                text=text,
                reply_id=reply_id,
                forwards=forwards,
                voices=voices,
                images=images,
                files=files,
                at_targets=at_targets,
                meta=meta,
            )
        )
        text = ctx.text
        content_type = ctx.content_type
        media = ctx.media
        at_user_id = self._self_uin if self._self_uin in at_targets else (at_targets[0] if at_targets else "")
        msg = SocialMessage(
            chat=Chat(chat_id=chat_id, chat_type=chat, chat_name=chat_name),
            sender=SocialSender(
                user_id=user_id,
                name=evt.sender.card if evt.sender.card is not None else evt.sender.nickname,
            ),
            type=content_type,
            text=text,
            media_url=media,
            media_urls=[str(image.get("url", "")) for image in images],
            media_descs=[str(image.get("summary", "")) for image in images],
            message_id=str(evt.message_id),
            timestamp=evt.time,
            at_user_id=at_user_id,
            to_ai=bool(self._self_uin) and (quote_user_id == self._self_uin or self._self_uin in at_targets),
            account_id=self.account_id,
            platform=self.name,
            meta=meta,
        )
        if content_type == ContentType.IMAGE:
            msg.media_desc = str(images[0].get("summary", ""))
        return msg

    # 补全消息内容
    async def hydrate_message(self, message: SocialMessage) -> SocialMessage:
        return await self._hydrate(message, ancestors=frozenset())

    # 补全引用和转发消息
    async def _hydrate(self, message: SocialMessage, ancestors: frozenset[tuple[str, str]]) -> SocialMessage:
        if message.type == ContentType.QUOTE:
            await self._hydrate_quote(message, ancestors)
        elif message.type == ContentType.FORWARD:
            await self._hydrate_forward(message, ancestors)
        return message

    # 补全引用消息
    async def _hydrate_quote(self, message: SocialMessage, ancestors: frozenset[tuple[str, str]]) -> None:
        reply_id = str(message.meta.pop("reply_message_id", "") or "")
        if not reply_id:
            return
        key = ("quote", reply_id)
        if key in ancestors:
            return
        reference = await self._get_message(reply_id)
        if reference is None:
            return
        message.quote_ref = await self._hydrate(reference, ancestors | {key})
        if self._self_uin and reference.sender.user_id == str(self._self_uin):
            message.to_ai = True

    # 补全合并转发消息
    async def _hydrate_forward(self, message: SocialMessage, ancestors: frozenset[tuple[str, str]]) -> None:
        key = ("forward", message.media_url or message.message_id or str(id(message)))
        if key in ancestors:
            return
        inline = message.meta.pop("forward_inline", None)
        nodes = inline if isinstance(inline, list) and inline else await self._get_forward_nodes(message.media_url)
        children: list[SocialMessage] = []
        for node in nodes:
            children.extend(self._node_messages(node))
        message.sub_messages = await asyncio.gather(*(self._hydrate(child, ancestors | {key}) for child in children))

    # 获取消息
    async def _get_message(self, message_id: str) -> SocialMessage | None:
        value: int | str = int(message_id) if message_id.lstrip("-").isdigit() else message_id
        response = await self._http_client.post(
            f"{self._http_url}/get_msg",
            json={"message_id": value},
            timeout=self._message_timeout_sec,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return self._to_message(NapCatMessageEvent.model_validate(data)) if data is not None else None

    # 获取转发消息节点列表
    async def _get_forward_nodes(self, forward_id: str) -> list[dict]:
        if not forward_id:
            return []
        response = await self._http_client.post(
            f"{self._http_url}/get_forward_msg",
            json={"id": forward_id},
            timeout=self._forward_timeout_sec,
        )
        response.raise_for_status()
        return list(response.json()["data"]["messages"])

    # 解析转发节点消息
    def _node_messages(self, node: dict) -> list[SocialMessage]:
        primary = self._to_message(node)
        if primary is None:
            return []
        return [primary]

    # 发送消息
    async def send(self, request: SocialSendRequest) -> SocialSendResponse:
        if request.account_id != self.account_id:
            raise ValueError("account_id 与 QQ 登录账号不匹配")
        chat_id = request.chat.chat_id
        chat_type = request.chat.chat_type.value
        text = request.text
        sticker = request.sticker
        voice = request.voice
        if not chat_id or (not text and not sticker and not voice):
            raise ValueError("缺少 chat_id 或内容")
        action = SendAction.PRIVATE_MSG.value if chat_type == ChatType.PRIVATE.value else SendAction.GROUP_MSG.value
        message_segments: list[dict] = []
        reply_to = request.reply_to_message_id
        if reply_to.lstrip("-").isdigit():
            message_segments.append({"type": SegmentType.REPLY.value, "data": {"id": int(reply_to)}})
        if text:
            message_segments.append({"type": SegmentType.TEXT.value, "data": {"text": text}})
        if sticker:
            message_segments.append({"type": SegmentType.IMAGE.value, "data": {"file": sticker.get("image_url", "")}})
        if voice:
            audio_path = voice.get("audio_path", "")
            napcat_path = audio_path.replace("/app/data/voice", "/app/audio")
            message_segments.append({"type": SegmentType.RECORD.value, "data": {"file": napcat_path}})
        payload: dict = {"message": message_segments}
        if chat_type == ChatType.PRIVATE.value:
            payload["user_id"] = int(chat_id)
        else:
            payload["group_id"] = int(chat_id)
        response = await self._http_client.post(
            f"{self._http_url}/{action}",
            json=payload,
            timeout=self._message_timeout_sec,
        )
        response.raise_for_status()
        data = response.json()
        if data["status"] != "ok":
            raise RuntimeError(str(data["message"]))
        return SocialSendResponse(message_id=str(data["data"]["message_id"]))

    # 获取 NapCat 的当前群成员快照
    async def list_group_members(self, chat_id: str) -> list[dict]:
        if not chat_id:
            raise ValueError("chat_id 不能为空")
        response = await self._http_client.post(
            f"{self._http_url}/get_group_member_list",
            json={"group_id": int(chat_id), "no_cache": False},
            timeout=self._message_timeout_sec,
        )
        response.raise_for_status()
        return [
            {
                "platform_user_id": str(member["user_id"]),
                "nickname": str(member["nickname"]),
                "group_card": str(member["card"]),
                "role": str(member["role"]),
            }
            for member in response.json()["data"]
        ]

    async def list_contacts(self, timeout_sec: float) -> dict[str, str]:
        response = await self._http_client.post(
            f"{self._http_url}/get_friend_list",
            json={},
            timeout=timeout_sec,
        )
        response.raise_for_status()
        return {
            str(friend["user_id"]): str(friend["remark"] or friend["nickname"]) for friend in response.json()["data"]
        }

    # 返回渠道能力
    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            channel=ChannelEnum.QQ.value,
            send_types=["text", "image", "sticker", "voice"],
            receive_types=["text", "image", "voice", "sticker", "forward", "quote", "file", "at"],
            supports_history=False,
            is_live_platform=False,
            supports_multi_ai=False,
        )
