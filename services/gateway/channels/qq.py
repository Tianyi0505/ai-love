
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import websockets

from services.gateway.channels.base import Channel, ChannelCapabilities, channel_registry
from services.gateway.enums import Channel as ChannelEnum, EventPostType, SegmentType, SendAction
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.infrastructure.runtime_config import required_value

logger = logging.getLogger("ailove.gateway.qq")


@channel_registry.register(ChannelEnum.QQ.value)
class QQChannel(Channel):
    name = ChannelEnum.QQ.value

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

    async def start(self) -> None:
        while not self._stop:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    print(f"[qq] 已连接 NapCat WS: {self._ws_url}")
                    async for raw in ws:
                        evt = json.loads(raw)
                        msg = self._to_message(evt)
                        if msg and self._on_message:
                            await self._on_message(msg)
            except Exception as e:
                print(f"[qq] WS 断开: {e}，重连中...")
                await asyncio.sleep(self._reconnect_delay_sec)

    async def stop(self) -> None:
        self._stop = True

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
        meta: dict = {}
        if reply_id:
            content_type = ContentType.QUOTE
            media = ""
            meta["reply_message_id"] = reply_id
        elif forwards:
            content_type = ContentType.FORWARD
            media = str(forwards[0].get("id", ""))
            inline = forwards[0].get("content")
            if isinstance(inline, list):
                meta["forward_inline"] = inline
        elif voices:
            content_type = ContentType.VOICE
            media = str(voices[0].get("url", ""))
        elif images:
            content_type = ContentType.IMAGE
            media = str(images[0].get("url", ""))
        elif files:
            content_type = ContentType.FILE
            media = str(files[0].get("url") or files[0].get("file") or "")
            text = text or str(files[0].get("name") or "文件")
        elif at_targets:
            content_type = ContentType.AT
            media = ""
        else:
            content_type = ContentType.TEXT
            media = ""
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

    async def hydrate_message(self, message: SocialMessage) -> SocialMessage:
        return await self._hydrate(message, ancestors=frozenset())

    async def _hydrate(self, message: SocialMessage, ancestors: frozenset[tuple[str, str]]) -> SocialMessage:
        reply_id = str(message.meta.pop("reply_message_id", "") or "")
        if message.type == ContentType.QUOTE and reply_id:
            key = ("quote", reply_id)
            if key not in ancestors:
                reference = await self._get_message(reply_id)
                if reference is not None:
                    message.quote_ref = await self._hydrate(reference, ancestors | {key})
                    if self._self_uin and reference.sender.user_id == str(self._self_uin):
                        message.to_ai = True
        if message.type == ContentType.FORWARD:
            key = ("forward", message.media_url or message.message_id or str(id(message)))
            if key in ancestors:
                return message
            inline = message.meta.pop("forward_inline", None)
            nodes = inline if isinstance(inline, list) and inline else await self._get_forward_nodes(message.media_url)
            children: list[SocialMessage] = []
            for node in nodes:
                children.extend(self._node_messages(node))
            message.sub_messages = await asyncio.gather(
                *(self._hydrate(child, ancestors | {key}) for child in children)
            )
        return message

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

    def _node_messages(self, node: dict) -> list[SocialMessage]:
        primary = self._to_message(node)
        if primary is None:
            return []
        return [primary]

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

    async def list_history(self, chat: Chat, since: int, limit: int) -> list[SocialMessage]:
        # 缓存本地聊天历史
        return []

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
