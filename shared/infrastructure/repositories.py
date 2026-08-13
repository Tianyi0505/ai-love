
from __future__ import annotations

from dataclasses import dataclass
import json
import time
import uuid

from shared.contracts.events import make_conversation_id
from shared.contracts.relationship import GroupRelationship, PersonRelationship
from shared.infrastructure.database import Database


# 表示AI档案记录数据
@dataclass(frozen=True)
class AIProfileRecord:
    ai_id: str
    definition_version: int


# 管理AI档案存储库持久化
class AIProfileRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 列出启用的配置
    async def list_active(self) -> list[AIProfileRecord]:
        rows = await self._db.fetch(
            "SELECT ai_id, definition_version "
            "FROM ai_profiles WHERE status='active' ORDER BY ai_id"
        )
        return [AIProfileRecord(row["ai_id"], row["definition_version"]) for row in rows]


# 管理账号归属存储库持久化
class AccountOwnershipRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 获取社交账号所属智能体
    async def owner_for_social_account(self, account_id: str) -> str | None:

        row = await self._db.fetchrow(
            "SELECT b.ai_id "
            "FROM ai_account_bindings b "
            "JOIN social_accounts a ON a.account_id=b.account_id "
            "WHERE b.account_id=$1 AND b.ended_at IS NULL "
            "AND a.allows_multi_ai=false",
            account_id,
        )
        return row["ai_id"] if row else None

    # 选择直播互动候选人
    async def live_candidates(self, account_id: str) -> list[str]:
        rows = await self._db.fetch(
            "SELECT ai_id FROM ai_account_bindings "
            "WHERE account_id=$1 AND ended_at IS NULL ORDER BY ai_id",
            account_id,
        )
        return [row["ai_id"] for row in rows]

    # 列出智能体绑定的账号
    async def accounts_for_ai(self, ai_id: str) -> list[str]:
        rows = await self._db.fetch(
            "SELECT account_id FROM ai_account_bindings "
            "WHERE ai_id=$1 AND ended_at IS NULL ORDER BY bound_at",
            ai_id,
        )
        return [row["account_id"] for row in rows]


# 管理身份存储库持久化
class IdentityRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 解析联系人
    async def resolve_person(
        self,
        platform: str,
        account_id: str,
        platform_user_id: str,
    ) -> tuple[str, str] | None:
        row = await self._db.fetchrow(
            "SELECT identity_id::text, person_id::text FROM platform_identities "
            "WHERE platform=$1 AND account_id=$2 AND platform_user_id=$3",
            platform,
            account_id,
            platform_user_id,
        )
        if row is None:
            return None
        return row["identity_id"], row["person_id"]

    # 解析或创建平台身份
    async def resolve_or_create(
        self,
        platform: str,
        account_id: str,
        platform_user_id: str,
        display_name: str = "",
    ) -> tuple[str, str]:
        existing = await self.resolve_person(platform, account_id, platform_user_id)
        if existing is not None:
            if display_name:
                await self._db.execute(
                    "UPDATE persons SET display_name=$2 WHERE person_id=$1::uuid "
                    "AND (display_name IS NULL OR display_name='')",
                    existing[1],
                    display_name,
                )
            return existing
        identity_id = str(uuid.uuid4())
        person_id = str(uuid.uuid4())
        async with self._db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT identity_id::text, person_id::text FROM platform_identities "
                    "WHERE platform=$1 AND account_id=$2 AND platform_user_id=$3 FOR UPDATE",
                    platform,
                    account_id,
                    platform_user_id,
                )
                if row is not None:
                    return row["identity_id"], row["person_id"]
                await conn.execute(
                    "INSERT INTO persons(person_id, display_name) VALUES($1::uuid, $2)",
                    person_id,
                    display_name,
                )
                await conn.execute(
                    "INSERT INTO platform_identities("
                    "identity_id, person_id, platform, account_id, platform_user_id, verified_by"
                    ") VALUES($1::uuid, $2::uuid, $3, $4, $5, 'platform-observed')",
                    identity_id,
                    person_id,
                    platform,
                    account_id,
                    platform_user_id,
                )
        return identity_id, person_id


# 管理会话存储库持久化
class ConversationRepository:

    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 记录入站消息
    async def record_inbound(self, message, ai_id: str) -> str:
        conversation_id = await self._conversation(
            message.platform,
            message.account_id,
            message.chat.chat_id,
            message.chat.chat_type.value,
            message.meta.get("conversation_id", ""),
        )
        platform_message_id = str(message.message_id or "")
        message_id = self._message_id(
            f"in:{message.platform}:{message.account_id}:{platform_message_id}"
            if platform_message_id
            else ""
        )
        occurred_at = float(message.timestamp or time.time())
        content = {
            "type": message.type.value,
            "text": message.text,
            "media_url": message.media_url,
            "media_desc": message.media_desc,
            "media_urls": message.media_urls,
            "media_descs": message.media_descs,
            "platform_message_id": platform_message_id,
        }
        await self._db.execute(
            "INSERT INTO messages(message_id,conversation_id,ai_id,platform_identity_id,role,content,"
            "occurred_at,retain_until,correlation_id) VALUES($1::uuid,$2::uuid,$3,$4::uuid,'user',"
            "$5::jsonb,to_timestamp($6),to_timestamp($6)+interval '180 days',$7) "
            "ON CONFLICT(message_id) DO NOTHING",
            message_id,
            conversation_id,
            ai_id,
            message.meta.get("platform_identity_id") or None,
            json.dumps(content, ensure_ascii=False),
            occurred_at,
            platform_message_id or message_id,
        )
        return conversation_id

    # 记录出站消息
    async def record_outbound(self, request: dict, result: dict, ai_id: str) -> str:
        chat = request.get("chat", {})
        platform = str(request.get("channel") or "qq")
        account_id = str(request.get("account_id") or "")
        conversation_id = await self._conversation(
            platform,
            account_id,
            str(chat.get("chat_id") or ""),
            str(chat.get("chat_type") or "private"),
            str(request.get("conversation_id") or ""),
        )
        platform_message_id = str(result.get("message_id") or "")
        message_id = self._message_id(
            f"out:{platform}:{account_id}:{platform_message_id}" if platform_message_id else ""
        )
        content = {
            "type": str(request.get("type") or "text"),
            "text": str(request.get("text") or ""),
            "has_sticker": bool(request.get("sticker")),
            "has_voice": bool(request.get("voice")),
            "platform_message_id": platform_message_id,
        }
        now = time.time()
        await self._db.execute(
            "INSERT INTO messages(message_id,conversation_id,ai_id,role,content,occurred_at,retain_until,"
            "correlation_id) VALUES($1::uuid,$2::uuid,$3,'assistant',$4::jsonb,to_timestamp($5),"
            "to_timestamp($5)+interval '180 days',$6) ON CONFLICT(message_id) DO NOTHING",
            message_id,
            conversation_id,
            ai_id,
            json.dumps(content, ensure_ascii=False),
            now,
            platform_message_id or message_id,
        )
        return conversation_id

    # 获取或创建会话上下文
    async def _conversation(
        self,
        platform: str,
        account_id: str,
        platform_chat_id: str,
        chat_type: str,
        requested_id: str,
    ) -> str:
        try:
            conversation_id = str(uuid.UUID(requested_id))
        except (ValueError, TypeError, AttributeError):
            conversation_id = make_conversation_id(platform, account_id, platform_chat_id)
        row = await self._db.fetchrow(
            "INSERT INTO conversations(conversation_id,platform,account_id,platform_chat_id,chat_type) "
            "VALUES($1::uuid,$2,$3,$4,$5) "
            "ON CONFLICT(platform,account_id,platform_chat_id) DO UPDATE SET chat_type=EXCLUDED.chat_type "
            "RETURNING conversation_id::text",
            conversation_id,
            platform,
            account_id,
            platform_chat_id,
            chat_type,
        )
        return row["conversation_id"]

    # 提取消息标识
    @staticmethod
    def _message_id(seed: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, seed)) if seed else str(uuid.uuid4())


# 管理关系存储库持久化
class RelationshipRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 获取联系人
    async def get_person(self, ai_id: str, person_id: str):
        row = await self._db.fetchrow(
            "SELECT familiarity, affinity, trust, importance FROM person_relationships "
            "WHERE ai_id=$1 AND person_id=$2::uuid",
            ai_id,
            person_id,
        )
        return PersonRelationship(**dict(row)) if row else PersonRelationship()

    # 保存联系人
    async def save_person(self, ai_id: str, person_id: str, relationship, ceiling_policy: str = "default") -> None:
        await self._db.execute(
            "INSERT INTO person_relationships("
            "ai_id, person_id, familiarity, affinity, trust, importance, ceiling_policy, last_interaction_at"
            ") VALUES($1,$2::uuid,$3,$4,$5,$6,$7,now()) "
            "ON CONFLICT(ai_id, person_id) DO UPDATE SET "
            "familiarity=EXCLUDED.familiarity, affinity=EXCLUDED.affinity, "
            "trust=EXCLUDED.trust, importance=EXCLUDED.importance, "
            "ceiling_policy=EXCLUDED.ceiling_policy, last_interaction_at=now()",
            ai_id,
            person_id,
            relationship.familiarity,
            relationship.affinity,
            relationship.trust,
            relationship.importance,
            ceiling_policy,
        )

    # 确保联系人
    async def ensure_person(self, ai_id: str, person_id: str, ceiling_policy: str = "default") -> None:
        await self._db.execute(
            "INSERT INTO person_relationships("
            "ai_id, person_id, familiarity, affinity, trust, importance, ceiling_policy"
            ") VALUES($1,$2::uuid,0,0,0,0,$3) "
            "ON CONFLICT(ai_id, person_id) DO UPDATE SET ceiling_policy=EXCLUDED.ceiling_policy",
            ai_id,
            person_id,
            ceiling_policy,
        )

    # 获取群聊
    async def get_group(self, ai_id: str, account_id: str, group_id: str):
        row = await self._db.fetchrow(
            "SELECT familiarity, belonging, affinity, activity_willingness FROM group_relationships "
            "WHERE ai_id=$1 AND account_id=$2 AND platform_group_id=$3",
            ai_id,
            account_id,
            group_id,
        )
        return GroupRelationship(**dict(row)) if row else GroupRelationship()

    # 保存群聊
    async def save_group(self, ai_id: str, account_id: str, group_id: str, relationship, ceiling_policy: str = "default") -> None:
        await self._db.execute(
            "INSERT INTO group_relationships("
            "ai_id, account_id, platform_group_id, familiarity, belonging, affinity, "
            "activity_willingness, ceiling_policy, last_interaction_at"
            ") VALUES($1,$2,$3,$4,$5,$6,$7,$8,now()) "
            "ON CONFLICT(ai_id, account_id, platform_group_id) DO UPDATE SET "
            "familiarity=EXCLUDED.familiarity, belonging=EXCLUDED.belonging, "
            "affinity=EXCLUDED.affinity, activity_willingness=EXCLUDED.activity_willingness, "
            "ceiling_policy=EXCLUDED.ceiling_policy, last_interaction_at=now()",
            ai_id,
            account_id,
            group_id,
            relationship.familiarity,
            relationship.belonging,
            relationship.affinity,
            relationship.activity_willingness,
            ceiling_policy,
        )

    # 列出联系人列表
    async def list_people(self, ai_id: str) -> list[dict]:
        rows = await self._db.fetch(
            "SELECT r.person_id::text, p.display_name, pi.platform_user_id AS user_id, pi.account_id, "
            "r.familiarity, r.affinity, r.trust, r.importance, r.last_interaction_at "
            "FROM person_relationships r JOIN persons p ON p.person_id=r.person_id "
            "LEFT JOIN LATERAL (SELECT platform_user_id, account_id FROM platform_identities "
            "WHERE person_id=r.person_id ORDER BY verified_at DESC LIMIT 1) pi ON true "
            "WHERE r.ai_id=$1 ORDER BY r.last_interaction_at DESC",
            ai_id,
        )
        return [dict(row) for row in rows]
