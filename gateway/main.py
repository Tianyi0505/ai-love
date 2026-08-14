
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from gateway.channels import bilibili, qq, wechat
from gateway.channels.base import Channel, create_channel
from gateway.qzone import QZoneService
from gateway.social_router import SocialRouter, StaticOwnershipResolver
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
from shared.infrastructure.entity_grounding import EntityGroundingRepository
from shared.infrastructure.repositories import (
    AccountOwnershipRepository,
    ConversationRepository,
    IdentityRepository,
    RelationshipRepository,
)
from shared.infrastructure.service import BaseService
from shared.contracts.tools import ToolExecutionContext
from shared.contracts.turn import new_run_id
logger = logging.getLogger("ailove.gateway")

SUBJ_EVENT_AI = "ai.events.{ai_id}"
SUBJ_EVENT_ALL = "ai.events.all"
SUBJ_LIVE_EVENTS = "live.events"


# 转发不同社交渠道的消息
class GatewayService(BaseService):
    name = "gateway"

    # 启动服务
    async def on_start(self) -> None:
        self._channels: dict[str, Channel] = {}
        section = await self.cfg.section()
        self._gcfg = GlobalConfig(provider=self.cfg.nacos)
        await self._gcfg.load()
        self._timeouts = self._gcfg.section("timeouts")
        account_specs = self._account_specs(section)
        static_owners = {
            spec["account_id"]: spec["owner_ai_id"]
            for spec in account_specs
        }
        self._db = None
        if os.environ.get("AILOVE_DATABASE_URL"):
            self._db = Database()
            await self._db.connect()
            ownership = AccountOwnershipRepository(self._db)
            self._identities = IdentityRepository(self._db)
            self._relationships = RelationshipRepository(self._db)
            self._conversations = ConversationRepository(self._db)
            self._grounding = EntityGroundingRepository(
                self._db,
                float(self._gcfg.get("grounding", "mention_evidence_half_life_sec")),
            )
        else:
            ownership = StaticOwnershipResolver(static_owners)
            self._identities = None
            self._relationships = None
            self._conversations = None
            self._grounding = None
        self._social_router = SocialRouter(ownership)
        self._group_member_sync_at: dict[tuple[str, str], float] = {}

        self._qq_whitelist = self._user_id_set(self._gcfg.get("qq", "whitelist"))

        self._account_configs: dict[str, dict] = {}
        for spec in account_specs:
            kind = spec["adapter"]
            ch_cfg = {**spec["config"], "account_id": spec["account_id"]}
            if kind == "qq":
                ch_cfg.update(
                    message_timeout_sec=self._timeouts["qq_message_sec"],
                    forward_timeout_sec=self._timeouts["qq_forward_sec"],
                    reconnect_delay_sec=self._gcfg.get("qq", "reconnect_delay_sec"),
                )
            channel = create_channel(kind, ch_cfg)
            channel.set_message_handler(self._on_channel_message)
            self._channels[spec["account_id"]] = channel
            self._account_configs[spec["account_id"]] = {"adapter": kind, **ch_cfg}
            self.spawn(channel.start())

        await self._sync_qq_whitelist()

        await self.bus.reply(SUBJ_SOCIAL_SEND, self._on_social_send)
        await self.bus.reply(SUBJ_SOCIAL_HISTORY, self._on_history_request)
        await self.bus.reply("identity.resolve-people.request", self._on_resolve_people)
        await self.bus.reply("history.search-group.request", self._on_search_group_history)
        qq_account_id = next(
            (account_id for account_id, cfg in self._account_configs.items() if cfg["adapter"] == "qq"),
            "",
        )
        if qq_account_id:
            qq_cfg = self._account_configs[qq_account_id]
            self._qq_account_id = qq_account_id
            owner_ai_id = await self._social_router.owner_for(qq_account_id)
            definition = await NacosAgentDefinitionStore(self.cfg.nacos).load(owner_ai_id)
            proactive_schedule = BehaviorSchedule.from_config(definition.behavior_policy)
            self.spawn(
                QZoneService(
                    napcat_http_url=qq_cfg["http_url"],
                    gcfg=self._gcfg,
                    qq_uin=qq_cfg["uin"],
                    relationship_provider=self._relationship_profile,
                    comment_generator=self._generate_comment,
                    proactive_allowed=proactive_schedule.allows_proactive,
                    timeouts=self._timeouts,
                ).loop()
            )
            logger.info("[gateway] QQ空间定时任务已挂载")

    # 收集用户标识
    @staticmethod
    def _user_id_set(value) -> set[str]:
        if isinstance(value, dict):
            value = value.get("user_ids", [])
        if not isinstance(value, (list, tuple, set)):
            return set()
        return {str(user_id) for user_id in value if str(user_id)}

    # 生成账号配置列表
    @staticmethod
    def _account_specs(section: dict) -> list[dict]:
        specs = section["accounts"]
        if not isinstance(specs, list):
            raise ValueError("service.gateway.accounts 必须是列表")
        result = [dict(spec) for spec in specs if isinstance(spec, dict)]
        if len(result) != len(specs):
            raise ValueError("service.gateway.accounts 每项必须是对象")
        for spec in result:
            for key in ("account_id", "adapter", "owner_ai_id", "config"):
                if key not in spec:
                    raise ValueError(f"service.gateway.accounts 每项必须包含 {key}")
        return result

    # 同步QQ白名单
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
            base_url = str(cfg["http_url"]).rstrip("/")
            try:
                async with httpx.AsyncClient(timeout=float(self._timeouts["friend_list_sec"])) as client:
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

    # 加载关系档案
    async def _relationship_profile(self, user_id: str) -> dict:
        try:
            ai_id = await self._social_router.owner_for(self._qq_account_id)
            resp = await self.bus.request_json(
                "relationship.list.request",
                {"ai_id": ai_id},
                timeout=float(self._timeouts["relationship_list_sec"]),
            )
            relationships = resp.get("relationships", [])
            top_familiarity = max((float(p.get("familiarity", 0.0)) for p in relationships), default=0.0)
            whitelist = self._user_id_set(self._gcfg.get("qq", "whitelist"))
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

    # 生成动态评论
    async def _generate_comment(
        self,
        feed_text: str,
        author_name: str,
        picture_urls: list[str],
    ) -> str:
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
                    "picture_urls": picture_urls,
                },
                timeout=float(self._timeouts["comment_generation_sec"]),
            )
            text = resp.get("comment", "")
            if text:
                return text
        except Exception as e:
            logger.warning("[gateway] 评论生成失败: %s", e)
        return ""

    # 停止服务
    async def on_stop(self) -> None:
        for channel in self._channels.values():
            await channel.stop()
        if self._db is not None:
            await self._db.close()

    # 处理渠道消息
    async def _on_channel_message(self, msg: SocialMessage) -> None:
        msg.meta["run_id"] = new_run_id()
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
        msg.meta["ai_id"] = turn.ai_id
        msg.meta["conversation_id"] = turn.conversation_id
        if msg.chat.chat_type == ChatType.GROUP and self._grounding is not None:
            try:
                await self._sync_group_members(msg)
                context = self._message_tool_context(msg, turn.ai_id)
                msg.meta["entity_context"] = (
                    await self._grounding.fast_ground(
                        context,
                        msg,
                        recent_participants_limit=int(
                            self._gcfg.get("grounding", "recent_participants_limit")
                        ),
                        recent_lookback_sec=int(
                            self._gcfg.get("grounding", "recent_participants_lookback_sec")
                        ),
                    )
                ).to_dict()
                await self._record_explicit_at_evidence(msg, context)
            except Exception:
                logger.exception("[gateway] 群聊实体上下文构建失败，继续投递原消息")
        if self._conversations is not None:
            await self._conversations.record_inbound(msg, turn.ai_id)
        await self.bus.publish_json(SUBJ_SOCIAL_CHAT.format(ai_id=turn.ai_id), msg.to_dict())

    # 按配置周期刷新群成员角色和群名片
    async def _sync_group_members(self, msg: SocialMessage) -> None:
        key = (msg.account_id, msg.chat.chat_id)
        now = time.monotonic()
        refresh_sec = float(self._gcfg.get("qq", "group_member_refresh_sec"))
        if now - self._group_member_sync_at.get(key, 0.0) < refresh_sec:
            return
        channel = self._channels.get(msg.account_id)
        if channel is None:
            return
        members = await channel.list_group_members(msg.chat.chat_id)
        if not members:
            return
        identities = await self._identities.resolve_or_create_many(
            msg.platform,
            msg.account_id,
            members,
        )
        snapshot = []
        for member in members:
            user_id = str(member["platform_user_id"])
            identity = identities.get(user_id)
            if identity is None:
                continue
            snapshot.append({**member, "person_id": identity[1]})
        await self._grounding.sync_group_members(
            msg.platform,
            msg.account_id,
            msg.chat.chat_id,
            snapshot,
        )
        self._group_member_sync_at[key] = now

    # 记录平台 @ 携带的称呼证据
    async def _record_explicit_at_evidence(
        self,
        msg: SocialMessage,
        context: ToolExecutionContext,
    ) -> None:
        for mention in msg.meta.get("at_mentions", []):
            name = str(mention.get("name") or "").strip()
            user_id = str(mention.get("user_id") or "")
            if (
                not name
                or name in {"群主", "管理员", "群管理员"}
                or (msg.to_ai and user_id == msg.at_user_id)
            ):
                continue
            result = await self._grounding.resolve_people(context, user_id, 1)
            candidates = result.get("candidates") or []
            if not candidates:
                continue
            await self._grounding.record_mention_evidence(
                mention_text=name,
                person_id=str(candidates[0]["person_id"]),
                scope_type="group",
                scope_id=context.chat_id,
                conversation_id=context.conversation_id,
                source_message_id=msg.message_id,
                evidence_type="explicit_at",
                confidence=1.0,
            )

    @staticmethod
    def _message_tool_context(msg: SocialMessage, ai_id: str) -> ToolExecutionContext:
        return ToolExecutionContext(
            ai_id=ai_id,
            account_id=msg.account_id,
            conversation_id=str(msg.meta.get("conversation_id") or ""),
            platform=msg.platform,
            chat_type=msg.chat.chat_type.value,
            chat_id=msg.chat.chat_id,
            sender_person_id=str(msg.meta.get("person_id") or ""),
        )

    # 校验系统注入的当前群作用域与真实会话、账号归属一致
    async def _valid_group_tool_context(self, context: ToolExecutionContext) -> bool:
        if self._grounding is None or not context.is_group:
            return False
        owner = await self._social_router.owner_for(context.account_id)
        return owner == context.ai_id and await self._grounding.context_matches(context)

    # 解析当前群里的称呼候选
    async def _on_resolve_people(self, payload: bytes) -> bytes:
        request = json.loads(payload.decode("utf-8"))
        context = ToolExecutionContext.from_dict(request.get("context"))
        arguments = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
        if not await self._valid_group_tool_context(context):
            return json.dumps({"ok": False, "error": "当前工具不具备有效群聊作用域"}, ensure_ascii=False).encode()
        mention = str(arguments.get("mention") or "").strip()
        limit = int(self._gcfg.get("grounding", "candidate_limit"))
        result = await self._grounding.resolve_people(context, mention, limit)
        return json.dumps({"ok": True, **result}, ensure_ascii=False).encode()

    # 仅检索当前群会话历史，并随结果返回发送者实体
    async def _on_search_group_history(self, payload: bytes) -> bytes:
        request = json.loads(payload.decode("utf-8"))
        context = ToolExecutionContext.from_dict(request.get("context"))
        arguments = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
        if not await self._valid_group_tool_context(context):
            return json.dumps({"ok": False, "error": "当前工具不具备有效群聊作用域"}, ensure_ascii=False).encode()
        default_limit = int(self._gcfg.get("grounding", "history_default_limit"))
        max_limit = int(self._gcfg.get("grounding", "history_max_limit"))
        limit = min(max_limit, max(1, int(arguments.get("limit") or default_limit)))
        messages = await self._grounding.search_group_history(
            context,
            str(arguments.get("query") or "").strip(),
            limit,
            int(self._gcfg.get("grounding", "history_lookback_sec")),
        )
        return json.dumps({"ok": True, "messages": messages}, ensure_ascii=False).encode()

    # 转换为互动事件
    async def _as_interaction(self, msg: SocialMessage) -> None:
        evt = InteractionEvent(
            type=InteractionType(
                msg.meta.get(
                    "bili_type",
                    str(self._gcfg.get("live", "default_interaction_type")),
                )
            ),
            actor=Viewer(uid=int(msg.sender.user_id or 0), name=msg.sender.name),
            importance=int(self._gcfg.get("live", "default_importance")),
            content=msg.text,
            meta=msg.meta,
            ai_target=msg.at_user_id or "",
            context_metadata={"account_id": msg.account_id},
        )
        await self.bus.publish_json(SUBJ_LIVE_EVENTS, evt.to_dict())

    # 处理社交发送
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

    # 处理历史请求
    async def _on_history_request(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        channel = self._channels.get(req.get("account_id", ""))
        if channel is None:
            return json.dumps({"messages": [], "has_more": False}).encode()
        msgs = await channel.list_history(
            req.get("chat", {}),
            since=req.get("since", int(self._gcfg.get("social", "channel_history_since"))),
            limit=req.get("limit", int(self._gcfg.get("social", "channel_history_limit"))),
        )
        return json.dumps({"messages": [m.to_dict() for m in msgs], "has_more": False}).encode()


# 启动程序入口
def main() -> None:
    # 运行主流程
    async def run() -> None:
        svc = GatewayService(await ServiceConfig.load("gateway"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
