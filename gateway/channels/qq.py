
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import websockets

from gateway.channels.base import Channel, ChannelCapabilities, channel_registry
from gateway.channels.content import ContentContext, content_registry
from gateway.enums import Channel as ChannelEnum, EventPostType, SegmentType, SendAction
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.infrastructure.runtime_config import required_value

logger = logging.getLogger("ailove.gateway.qq")


# 接入QQ消息收发渠道
@channel_registry.register(ChannelEnum.QQ.value)
class QQChannel(Channel):
    name = ChannelEnum.QQ.value

    # 初始化当前实例
    def __init__(self, cfg: dict) -> None:
        super().__init__(cfg)
        self._ws_url = required_value(cfg["ws_url"], "service.gateway QQ ws_url")
        self._http_url = required_value(cfg["http_url"], "service.gateway QQ http_url")
        self._self_uin = required_value(
            str(cfg["uin"]),
            "service.gateway QQ uin",
        )
        self.account_id = str(cfg["account_id"])
        self._message_timeout_sec = float(cfg["message_timeout_sec"])
        self._forward_timeout_sec = float(cfg["forward_timeout_sec"])
        self._reconnect_delay_sec = float(cfg["reconnect_delay_sec"])
        self._ws = None
        self._stop = False
        self._queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}

    # 启动服务
    async def start(self) -> None:
        while not self._stop:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    print(f"[qq] 已连接 NapCat WS: {self._ws_url}")
                    async for raw in ws:
                        evt = json.loads(raw)
                        msg = self._to_message(evt)
                        if msg is None:
                            continue
                        if self._on_message is None:
                            logger.warning("[qq] 收到消息但未设置消息处理器，已丢弃: message_id=%s", msg.message_id)
                            continue
                        self._dispatch(msg)
            except Exception as e:
                print(f"[qq] WS 断开: {e}，重连中...")
                await asyncio.sleep(self._reconnect_delay_sec)
        await self._stop_workers()

    # 停止服务
    async def stop(self) -> None:
        self._stop = True

    # 按会话分发消息：不同会话并行，同一会话内串行
    def _dispatch(self, msg: SocialMessage) -> None:
        key = f"{msg.account_id}:{msg.chat.chat_type.value}:{msg.chat.chat_id}"
        queue = self._queues.get(key)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[key] = queue
            self._workers[key] = asyncio.create_task(self._run_session(key, queue))
        queue.put_nowait(msg)

    # 单会话消息顺序处理循环
    async def _run_session(self, key: str, queue: asyncio.Queue) -> None:
        while True:
            msg = await queue.get()
            try:
                await asyncio.wait_for(self._on_message(msg), timeout=self._message_timeout_sec)
            except asyncio.TimeoutError:
                logger.error("[qq] 会话消息处理超时，已跳过: key=%s message_id=%s", key, msg.message_id)
            except Exception:
                logger.exception("[qq] 会话消息处理异常，已跳过: key=%s message_id=%s", key, msg.message_id)
            finally:
                queue.task_done()

    # 终止所有会话 worker
    async def _stop_workers(self) -> None:
        for task in self._workers.values():
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()
        self._queues.clear()

    # 转换为消息
    def _to_message(self, evt: dict) -> SocialMessage | None:
        if evt.get("post_type") != EventPostType.MESSAGE.value:
            return None
        segments = evt.get("message") or []
        if not isinstance(segments, list):
            segments = [{"type": SegmentType.TEXT.value, "data": {"text": str(segments)}}]
        msg_type = evt.get("message_type", ChatType.PRIVATE.value)
        user_id = str(evt.get("user_id", ""))
        text = "".join(
            str(seg.get("data", {}).get("text", ""))
            for seg in segments
            if seg.get("type") == SegmentType.TEXT.value
        ).strip()
        at_targets = [
            str(seg.get("data", {}).get("qq", "") or "")
            for seg in segments
            if seg.get("type") == SegmentType.AT.value and seg.get("data", {}).get("qq")
        ]
        at_mentions = [
            {
                "user_id": str(seg.get("data", {}).get("qq", "") or ""),
                "name": str(seg.get("data", {}).get("name", "") or ""),
            }
            for seg in segments
            if seg.get("type") == SegmentType.AT.value and seg.get("data", {}).get("qq")
        ]
        images = [
            seg.get("data", {})
            for seg in segments
            if seg.get("type") == SegmentType.IMAGE.value and seg.get("data", {}).get("url")
        ]
        voices = [
            seg.get("data", {})
            for seg in segments
            if seg.get("type") == SegmentType.RECORD.value and seg.get("data", {}).get("url")
        ]
        forwards = [
            seg.get("data", {})
            for seg in segments
            if seg.get("type") == SegmentType.FORWARD.value and seg.get("data", {}).get("id")
        ]
        files = [seg.get("data", {}) for seg in segments if seg.get("type") == "file"]
        reply_id = ""
        quote_user_id = ""
        for seg in segments:
            if seg.get("type") == SegmentType.REPLY.value:
                reply_id = str(seg.get("data", {}).get("id", "") or "")
                quote_user_id = str(seg.get("data", {}).get("user_id", ""))
                break
        if not text and not at_targets and not images and not voices and not forwards and not files and not reply_id:
            return None
        if msg_type == ChatType.PRIVATE.value:
            chat = ChatType.PRIVATE
            chat_id = user_id
            chat_name = evt.get("sender", {}).get("nickname", "")
        else:
            chat = ChatType.GROUP
            chat_id = str(evt.get("group_id", ""))
            chat_name = evt.get("group_name", "")
        meta: dict = {
            "at_user_ids": at_targets,
            "at_mentions": at_mentions,
            "sender_role": str(evt.get("sender", {}).get("role") or ""),
        }
        ctx = content_registry.resolve(
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
            sender=SocialSender(user_id=user_id, name=evt.get("sender", {}).get("card") or evt.get("sender", {}).get("nickname", "")),
            type=content_type,
            text=text,
            media_url=media,
            media_urls=[str(image.get("url", "")) for image in images],
            media_descs=[str(image.get("summary", "")) for image in images],
            message_id=str(evt.get("message_id", "")),
            timestamp=evt.get("time", 0),
            at_user_id=at_user_id,
            to_ai=bool(self._self_uin)
            and (quote_user_id == self._self_uin or self._self_uin in at_targets),
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
        message.sub_messages = await asyncio.gather(
            *(self._hydrate(child, ancestors | {key}) for child in children)
        )

    # 获取消息
    async def _get_message(self, message_id: str) -> SocialMessage | None:
        try:
            value: int | str = int(message_id) if message_id.lstrip("-").isdigit() else message_id
            async with httpx.AsyncClient(timeout=self._message_timeout_sec) as client:
                resp = await client.post(f"{self._http_url}/get_msg", json={"message_id": value})
                resp.raise_for_status()
            data = resp.json().get("data") or {}
            return self._to_message(data) if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning("[qq] 获取引用消息失败: %s", exc)
            return None

    # 获取转发消息节点列表
    async def _get_forward_nodes(self, forward_id: str) -> list[dict]:
        if not forward_id:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._forward_timeout_sec) as client:
                resp = await client.post(f"{self._http_url}/get_forward_msg", json={"id": forward_id})
                resp.raise_for_status()
            messages = (resp.json().get("data") or {}).get("messages") or []
            return [node for node in messages if isinstance(node, dict)]
        except Exception as exc:
            logger.warning("[qq] 获取合并转发失败: %s", exc)
            return []

    # 解析转发节点消息
    def _node_messages(self, node: dict) -> list[SocialMessage]:
        primary = self._to_message(node)
        if primary is None:
            return []
        return [primary]

    # 发送消息
    async def send(self, req) -> dict:
        if req.get("account_id") != self.account_id:
            return {"ok": False, "message_id": "", "fallback_note": "account_id 与 QQ 登录账号不匹配"}
        chat = req.get("chat", {})
        chat_id = chat.get("chat_id", "")
        chat_type = chat.get("chat_type", "private")
        text = req.get("text", "")
        sticker = req.get("sticker")
        voice = req.get("voice")
        if not chat_id or (not text and not sticker and not voice):
            return {"ok": False, "message_id": "", "fallback_note": "缺少 chat_id 或内容"}
        action = SendAction.PRIVATE_MSG.value if chat_type == ChatType.PRIVATE.value else SendAction.GROUP_MSG.value
        message_segments: list[dict] = []
        reply_to = str(req.get("reply_to_message_id") or "")
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
        async with httpx.AsyncClient(timeout=self._message_timeout_sec) as client:
            resp = await client.post(f"{self._http_url}/{action}", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            result_data = data.get("data") or {}
            ok = data.get("status") == "ok"
            return {
                "ok": ok,
                "message_id": str(result_data.get("message_id", "")),
                "fallback_note": "" if ok else str(data.get("message") or data.get("wording") or "NapCat 发送失败"),
            }
        return {"ok": False, "message_id": "", "fallback_note": f"HTTP {resp.status_code}"}

    # 列出历史
    async def list_history(self, chat: Chat, since: int, limit: int) -> list[SocialMessage]:
        # 缓存本地聊天历史
        return []

    # 获取 NapCat 的当前群成员快照
    async def list_group_members(self, chat_id: str) -> list[dict]:
        if not chat_id:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._message_timeout_sec) as client:
                response = await client.post(
                    f"{self._http_url}/get_group_member_list",
                    json={"group_id": int(chat_id), "no_cache": False},
                )
                response.raise_for_status()
            result = []
            for member in response.json().get("data") or []:
                user_id = str(member.get("user_id") or "")
                if not user_id:
                    continue
                role = str(member.get("role") or "member")
                if role not in {"owner", "admin", "member"}:
                    role = "member"
                result.append(
                    {
                        "platform_user_id": user_id,
                        "nickname": str(member.get("nickname") or ""),
                        "group_card": str(member.get("card") or ""),
                        "role": role,
                    }
                )
            return result
        except Exception as exc:
            logger.warning("[qq] 获取群成员失败: group=%s error=%s", chat_id, exc)
            return []

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
