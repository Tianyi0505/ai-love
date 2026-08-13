
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

import httpx

from services.gateway.channels import bilibili, qq, wechat  # noqa: F401
from services.gateway.channels.base import Channel, create_channel
from services.gateway.qzone import QZoneService
from services.gateway.social_router import SocialRouter, StaticOwnershipResolver
from shared.contracts.behavior import BehaviorSchedule
from shared.contracts.live import InteractionEvent, InteractionType, Viewer
from shared.contracts.social import (
    SUBJ_SOCIAL_CHAT,
    SUBJ_SOCIAL_HISTORY,
    SUBJ_SOCIAL_SEND,
    ChatType,
    ContentType,
    SocialMessage,
)
from shared.infrastructure.agent_store import NacosAgentDefinitionStore
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.database import Database
from shared.infrastructure.global_config import GlobalConfig
from shared.infrastructure.repositories import (
    AccountOwnershipRepository,
    ConversationRepository,
    IdentityRepository,
    RelationshipRepository,
)
from shared.infrastructure.service import BaseService
from shared.vision.base import create_describer

logger = logging.getLogger("ailove.gateway")

SUBJ_EVENT_AI = "ai.events.{ai_id}"
SUBJ_EVENT_ALL = "ai.events.all"
SUBJ_LIVE_EVENTS = "live.events"


class GatewayService(BaseService):
    name = "gateway"

    async def on_start(self) -> None:
        self._channels: dict[str, Channel] = {}
        section = await self.cfg.section()
        self._gcfg = GlobalConfig(provider=self.cfg.nacos)
        await self._gcfg.load()
        self._describer_kind = section.get("describer", "mcp_default")
        self._image_describer = create_describer(self._describer_kind)
        account_specs = self._account_specs(section)
        static_owners = {
            spec["account_id"]: spec.get("owner_ai_id", "")
            for spec in account_specs
            if spec.get("owner_ai_id")
        }
        self._db = None
        if os.environ.get("AILOVE_DATABASE_URL"):
            self._db = Database()
            await self._db.connect()
            ownership = AccountOwnershipRepository(self._db)
            self._identities = IdentityRepository(self._db)
            self._relationships = RelationshipRepository(self._db)
            self._conversations = ConversationRepository(self._db)
        else:
            ownership = StaticOwnershipResolver(static_owners)
            self._identities = None
            self._relationships = None
            self._conversations = None
        self._social_router = SocialRouter(ownership)

        whitelist = self._user_id_set(section.get("qq_whitelist", []))
        whitelist.update(self._user_id_set(self._gcfg.get("qq", "whitelist", [])))
        self._qq_whitelist = whitelist

        self._account_configs: dict[str, dict] = {}
        for spec in account_specs:
            kind = spec["adapter"]
            ch_cfg = {**spec.get("config", {}), "account_id": spec["account_id"]}
            channel = create_channel(kind, ch_cfg)
            channel.set_message_handler(self._on_channel_message)
            self._channels[spec["account_id"]] = channel
            self._account_configs[spec["account_id"]] = {"adapter": kind, **ch_cfg}
            self.spawn(channel.start())

        await self._sync_qq_whitelist()

        await self.bus.reply(SUBJ_SOCIAL_SEND, self._on_social_send)
        await self.bus.reply(SUBJ_SOCIAL_HISTORY, self._on_history_request)
        qq_account_id = next(
            (account_id for account_id, cfg in self._account_configs.items() if cfg["adapter"] == "qq"),
            "",
        )
        if qq_account_id:
            qq_cfg = self._account_configs[qq_account_id]
            self._qq_account_id = qq_account_id
            owner_ai_id = await self._social_router.owner_for(qq_account_id)
            try:
                definition = await NacosAgentDefinitionStore(self.cfg.nacos).load(owner_ai_id or "")
                proactive_schedule = BehaviorSchedule.from_config(definition.behavior_policy)
            except Exception:
                logger.exception("[gateway] 未能加载 QQ 所属 AI 的主动行为作息，QQ 空间主动互动保持关闭")
                proactive_schedule = BehaviorSchedule.from_config({})
            self.spawn(
                QZoneService(
                    napcat_http_url=qq_cfg["http_url"],
                    gcfg=self._gcfg,
                    qq_uin=qq_cfg.get("uin", ""),
                    relationship_provider=self._relationship_profile,
                    comment_generator=self._generate_comment,
                    proactive_allowed=proactive_schedule.allows_proactive,
                    image_describer=self._image_describer,
                ).loop()
            )
            logger.info("[gateway] QQ空间定时任务已挂载")

    @staticmethod
    def _user_id_set(value) -> set[str]:
        if isinstance(value, dict):
            value = value.get("user_ids", [])
        if not isinstance(value, (list, tuple, set)):
            return set()
        return {str(user_id) for user_id in value if str(user_id)}

    @staticmethod
    def _account_specs(section: dict) -> list[dict]:
        specs = section.get("accounts", [])
        if isinstance(specs, list) and specs:
            result = [dict(spec) for spec in specs if isinstance(spec, dict)]
            for spec in result:
                if not spec.get("account_id") or not spec.get("adapter"):
                    raise ValueError("gateway.accounts 每项必须包含 account_id 和 adapter")
            return result
        result = []
        for kind, config in section.get("channels", {}).items():
            result.append(
                {
                    "account_id": config.get("account_id", f"{kind}-main"),
                    "adapter": kind,
                    "owner_ai_id": config.get("owner_ai_id", section.get("default_ai_id", "")),
                    "config": dict(config),
                }
            )
        return result

    async def _sync_qq_whitelist(self) -> None:
        if self._identities is None or self._relationships is None or not self._qq_whitelist:
            return
        for account_id, cfg in self._account_configs.items():
            if cfg.get("adapter") != "qq":
                continue
            ai_id = await self._social_router.owner_for(account_id)
            if not ai_id:
                logger.warning("[gateway] 白名单身份未同步：账号 %s 没有绑定 AI", account_id)
                continue
            names: dict[str, str] = {}
            base_url = str(cfg.get("http_url", "")).rstrip("/")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(f"{base_url}/get_friend_list", json={})
                    response.raise_for_status()
                    for friend in response.json().get("data") or []:
                        user_id = str(friend.get("user_id") or "")
                        names[user_id] = str(friend.get("remark") or friend.get("nickname") or "")
            except Exception as exc:
                logger.warning("[gateway] 获取 QQ 好友昵称失败，白名单仍按 QQ 号落库: %s", exc)
            for user_id in self._qq_whitelist:
                _, person_id = await self._identities.resolve_or_create(
                    "qq", account_id, user_id, names.get(user_id) or user_id
                )
                await self._relationships.ensure_person(ai_id, person_id, "whitelist")
            logger.info("[gateway] 已同步 %s 个 QQ 白名单身份", len(self._qq_whitelist))

    async def _relationship_profile(self, user_id: str) -> dict:
        try:
            ai_id = await self._social_router.owner_for(self._qq_account_id)
            resp = await self.bus.request_json("relationship.list.request", {"ai_id": ai_id}, timeout=3.0)
            relationships = resp.get("relationships", [])
            top_familiarity = max((float(p.get("familiarity", 0.0)) for p in relationships), default=0.0)
            whitelist = self._user_id_set(self._gcfg.get("qq", "whitelist", []))
            for p in relationships:
                if str(p.get("user_id", "")) == str(user_id):
                    familiarity = float(p.get("familiarity", 0.0))
                    if str(user_id) in whitelist:
                        familiarity = max(familiarity, top_familiarity)
                    return {
                        "familiarity": familiarity,
                        "affinity": float(p.get("affinity", 0.0)),
                        "trust": float(p.get("trust", 0.0)),
                        "importance": float(p.get("importance", 0.0)),
                        "top_familiarity": top_familiarity,
                    }
        except Exception:
            pass
        return {"familiarity": 0.0, "affinity": 0.0, "trust": 0.0, "importance": 0.0}

    async def _generate_comment(self, feed_text: str, author_name: str) -> str:
        try:
            ai_id = await self._social_router.owner_for(self._qq_account_id)
            if not ai_id:
                return ""
            resp = await self.bus.request_json(
                "ai.comment.request",
                {
                    "ai_id": ai_id,
                    "account_id": self._qq_account_id,
                    "feed_text": feed_text,
                    "author_name": author_name,
                },
                timeout=15.0,
            )
            text = resp.get("comment", "")
            if text:
                return text
        except Exception as e:
            logger.warning("[gateway] 评论生成失败: %s", e)
        return ""

    async def on_stop(self) -> None:
        for channel in self._channels.values():
            await channel.stop()
        if self._db is not None:
            await self._db.close()

    async def _on_channel_message(self, msg: SocialMessage) -> None:
        if msg.platform == "qq":
            msg.meta["priority_contact"] = str(msg.sender.user_id) in self._qq_whitelist
        if msg.chat.chat_type == ChatType.GROUP and msg.chat.chat_id.startswith("live:"):
            await self._as_interaction(msg)
            return
        channel = self._channels.get(msg.account_id)
        if channel is not None:
            msg = await channel.hydrate_message(msg)
        if self._identities is not None:
            identity_id, person_id = await self._identities.resolve_or_create(
                msg.platform,
                msg.account_id,
                msg.sender.user_id,
                msg.sender.name,
            )
            msg.meta["platform_identity_id"] = identity_id
            msg.meta["person_id"] = person_id
        try:
            turn = await self._social_router.route(msg)
        except LookupError as exc:
            logger.warning("[gateway] 社交消息未路由: %s", exc)
            return
        if msg.all_media_urls():
            self.spawn(self._collect_stickers(msg, turn.ai_id))
        msg.meta["ai_id"] = turn.ai_id
        msg.meta["conversation_id"] = turn.conversation_id
        if self._conversations is not None:
            await self._conversations.record_inbound(msg, turn.ai_id)
        await self.bus.publish_json(SUBJ_SOCIAL_CHAT.format(ai_id=turn.ai_id), msg.to_dict())

    async def _collect_stickers(self, msg: SocialMessage, ai_id: str) -> None:
        await asyncio.gather(
            *(self._collect_sticker(image_url, ai_id) for image_url in msg.all_media_urls())
        )

    async def _collect_sticker(self, image_url: str, ai_id: str) -> None:
        try:
            desc = await self._image_describer.describe(image_url)
            min_quality = float(self._gcfg.get("sticker", "collect_min_quality", 0.65))
            if desc.match_quality < min_quality or not desc.sticker_description:
                logger.info("[gateway] 跳过非表情图片: quality=%.2f %s", desc.match_quality, desc.description[:30])
                return
            sticker_id = f"stk_{hashlib.md5(image_url.encode()).hexdigest()[:12]}"
            result = await self.bus.request_json(
                "sticker.add.request",
                {
                    "ai_id": ai_id,
                    "id": sticker_id,
                    "image_url": image_url,
                    "description": desc.sticker_description,
                    "tags": desc.tags,
                    "match_quality": desc.match_quality,
                },
                timeout=3.0,
            )
            if result.get("ok"):
                logger.info("[gateway] 收藏表情: %s", desc.description)
            else:
                logger.warning("[gateway] 表情收藏失败: %s", result.get("action", "unknown"))
        except Exception as e:
            logger.warning("[gateway] 收藏表情失败: %s", e)

    async def _as_interaction(self, msg: SocialMessage) -> None:
        evt = InteractionEvent(
            type=InteractionType(msg.meta.get("bili_type", "danmaku")),
            actor=Viewer(uid=int(msg.sender.user_id or 0), name=msg.sender.name),
            content=msg.text,
            meta=msg.meta,
            ai_target=msg.at_user_id or "",
            context_metadata={"account_id": msg.account_id},
        )
        await self.bus.publish_json(SUBJ_LIVE_EVENTS, evt.to_dict())

    async def _on_social_send(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        account_id = req.get("account_id", "")
        channel = self._channels.get(account_id)
        if channel is None:
            return json.dumps({"ok": False, "fallback_note": f"账号未启用或缺少 account_id: {account_id}"}).encode()
        result = await channel.send(req)
        if result.get("ok") and self._conversations is not None:
            ai_id = str(req.get("ai_id") or await self._social_router.owner_for(account_id) or "")
            if ai_id:
                try:
                    await self._conversations.record_outbound(req, result, ai_id)
                except Exception:
                    logger.exception("[gateway] 出站消息已发送，但持久化失败")
        elif not result.get("ok"):
            logger.warning(
                "[gateway] 渠道发送失败: account=%s chat_type=%s reason=%s",
                account_id,
                req.get("chat", {}).get("chat_type", ""),
                result.get("fallback_note", "unknown"),
            )
        return json.dumps(result).encode()

    async def _on_history_request(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        channel = self._channels.get(req.get("account_id", ""))
        if channel is None:
            return json.dumps({"messages": [], "has_more": False}).encode()
        msgs = await channel.list_history(req.get("chat", {}), since=req.get("since", 0), limit=req.get("limit", 50))
        return json.dumps({"messages": [m.to_dict() for m in msgs], "has_more": False}).encode()


def main() -> None:
    async def run() -> None:
        svc = GatewayService(await ServiceConfig.load("gateway"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
