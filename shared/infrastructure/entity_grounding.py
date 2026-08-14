from __future__ import annotations

import json
import re
import uuid

from shared.contracts.entity import EntityCandidate, EntityContext, EntityReference
from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure.database import Database


_ROLE_NAMES = {
    "群主": ("owner",),
    "管理员": ("admin",),
    "群管理员": ("admin",),
}


def normalize_mention(value: str) -> str:
    return re.sub(r"[\s@，,。.!！?？:：]+", "", value).casefold()


# 管理群成员快照与称呼证据
class EntityGroundingRepository:
    def __init__(self, db: Database, evidence_half_life_sec: float) -> None:
        self._db = db
        self._evidence_half_life_sec = evidence_half_life_sec

    async def context_matches(self, context: ToolExecutionContext) -> bool:
        if not (
            context.ai_id
            and context.account_id
            and context.conversation_id
            and context.platform
            and context.chat_type
            and context.chat_id
        ):
            return False
        row = await self._db.fetchrow(
            "SELECT EXISTS(SELECT 1 FROM conversations c WHERE c.conversation_id=$1::uuid "
            "AND c.platform=$2 AND c.account_id=$3 AND c.platform_chat_id=$4 AND c.chat_type=$5) AS exists",
            context.conversation_id,
            context.platform,
            context.account_id,
            context.chat_id,
            context.chat_type,
        )
        return bool(row["exists"])

    async def sync_group_members(
        self,
        platform: str,
        account_id: str,
        chat_id: str,
        members: list[dict],
    ) -> None:
        async with self._db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE group_members SET is_active=false WHERE platform=$1 "
                    "AND account_id=$2 AND chat_id=$3",
                    platform,
                    account_id,
                    chat_id,
                )
                for member in members:
                    await conn.execute(
                        "INSERT INTO group_members(platform,account_id,chat_id,platform_user_id,"
                        "person_id,nickname,group_card,role,is_active,last_seen_at) "
                        "VALUES($1,$2,$3,$4,$5::uuid,$6,$7,$8,true,now()) "
                        "ON CONFLICT(platform,account_id,chat_id,platform_user_id) DO UPDATE SET "
                        "person_id=EXCLUDED.person_id,nickname=EXCLUDED.nickname,"
                        "group_card=EXCLUDED.group_card,role=EXCLUDED.role,is_active=true,last_seen_at=now()",
                        platform,
                        account_id,
                        chat_id,
                        str(member["platform_user_id"]),
                        str(member["person_id"]),
                        str(member.get("nickname") or ""),
                        str(member.get("group_card") or ""),
                        str(member.get("role") or "member"),
                    )

    async def record_mention_evidence(
        self,
        *,
        mention_text: str,
        person_id: str,
        scope_type: str,
        scope_id: str,
        conversation_id: str = "",
        source_message_id: str = "",
        evidence_type: str,
        confidence: float,
    ) -> None:
        normalized = normalize_mention(mention_text)
        if not normalized or not person_id:
            return
        await self._db.execute(
            "INSERT INTO person_mentions(mention_id,mention_text,normalized_mention,person_id,"
            "scope_type,scope_id,conversation_id,source_message_id,evidence_type,confidence) "
            "VALUES($1::uuid,$2,$3,$4::uuid,$5,$6,$7::uuid,$8,$9,$10) "
            "ON CONFLICT(normalized_mention,person_id,scope_type,scope_id,evidence_type,source_message_id) "
            "DO UPDATE SET confidence=GREATEST(person_mentions.confidence,EXCLUDED.confidence),"
            "observed_at=now()",
            str(uuid.uuid4()),
            mention_text.strip(),
            normalized,
            person_id,
            scope_type,
            scope_id,
            conversation_id or None,
            source_message_id,
            evidence_type,
            max(0.0, min(1.0, confidence)),
        )

    async def resolve_people(
        self,
        context: ToolExecutionContext,
        mention: str,
        limit: int,
    ) -> dict:
        normalized = normalize_mention(mention)
        if not normalized:
            return {"mention": mention, "candidates": []}

        candidates: dict[str, dict] = {}
        roles = _ROLE_NAMES.get(normalized)
        if roles:
            rows = await self._db.fetch(
                "SELECT gm.person_id::text,COALESCE(NULLIF(gm.group_card,''),"
                "NULLIF(gm.nickname,''),p.display_name,'') AS display_name,gm.role "
                "FROM group_members gm JOIN persons p ON p.person_id=gm.person_id "
                "WHERE gm.platform=$1 AND gm.account_id=$2 AND gm.chat_id=$3 "
                "AND gm.is_active AND gm.role=ANY($4::text[]) ORDER BY gm.role,display_name",
                context.platform,
                context.account_id,
                context.chat_id,
                list(roles),
            )
            for row in rows:
                self._add_candidate(
                    candidates,
                    row["person_id"],
                    row["display_name"],
                    1.0 if len(rows) == 1 else 0.9,
                    {"type": "group_role", "role": row["role"]},
                )
        else:
            rows = await self._db.fetch(
                "SELECT gm.person_id::text,COALESCE(NULLIF(gm.group_card,''),"
                "NULLIF(gm.nickname,''),p.display_name,'') AS display_name,"
                "gm.platform_user_id,gm.nickname,gm.group_card "
                "FROM group_members gm JOIN persons p ON p.person_id=gm.person_id "
                "WHERE gm.platform=$1 AND gm.account_id=$2 AND gm.chat_id=$3 AND gm.is_active "
                "AND (lower(gm.platform_user_id)=lower($4) OR lower(gm.nickname)=lower($5) "
                "OR lower(gm.group_card)=lower($5) OR lower(p.display_name)=lower($5))",
                context.platform,
                context.account_id,
                context.chat_id,
                mention.strip().lstrip("@"),
                mention.strip(),
            )
            for row in rows:
                if row["platform_user_id"].casefold() == mention.strip().lstrip("@").casefold():
                    confidence, evidence_type = 1.0, "platform_identity"
                elif str(row["group_card"]).casefold() == mention.strip().casefold():
                    confidence, evidence_type = 0.98, "group_card"
                else:
                    confidence, evidence_type = 0.95, "display_name"
                self._add_candidate(
                    candidates,
                    row["person_id"],
                    row["display_name"],
                    confidence,
                    {"type": evidence_type},
                )

            evidence_rows = await self._db.fetch(
                "SELECT pm.person_id::text,p.display_name,MAX(pm.confidence) AS confidence,"
                "COUNT(*)::int AS evidence_count,MAX(pm.observed_at) AS last_seen_at,"
                "EXTRACT(EPOCH FROM now()-MAX(pm.observed_at)) AS age_sec "
                "FROM person_mentions pm JOIN persons p ON p.person_id=pm.person_id "
                "JOIN group_members gm ON gm.person_id=pm.person_id AND gm.platform=$2 "
                "AND gm.account_id=$3 AND gm.chat_id=$4 AND gm.is_active "
                "WHERE pm.normalized_mention=$1 AND ((pm.scope_type='group' AND pm.scope_id=$4) "
                "OR (pm.scope_type='conversation' AND pm.scope_id=$6) OR pm.scope_type='global') "
                "GROUP BY pm.person_id,p.display_name "
                "ORDER BY confidence DESC,evidence_count DESC,last_seen_at DESC LIMIT $5",
                normalized,
                context.platform,
                context.account_id,
                context.chat_id,
                limit,
                context.conversation_id,
            )
            for row in evidence_rows:
                recency = 0.5 ** (
                    max(0.0, float(row["age_sec"] or 0.0)) / self._evidence_half_life_sec
                )
                confidence = min(
                    0.99,
                    float(row["confidence"]) * recency
                    + min(0.12, int(row["evidence_count"]) * 0.02),
                )
                self._add_candidate(
                    candidates,
                    row["person_id"],
                    row["display_name"],
                    confidence,
                    {
                        "type": "mention_evidence",
                        "count": int(row["evidence_count"]),
                        "last_seen_at": str(row["last_seen_at"]),
                    },
                )

        ordered = sorted(
            candidates.values(),
            key=lambda item: (-item["confidence"], item["display_name"], item["person_id"]),
        )[:limit]
        return {"mention": mention, "candidates": ordered}

    async def fast_ground(
        self,
        context: ToolExecutionContext,
        message,
        recent_participants_limit: int = 6,
        recent_lookback_sec: int = 86400,
    ) -> EntityContext:
        sender = (
            {
                "person_id": context.sender_person_id,
                "display_name": message.sender.name or message.sender.user_id,
            }
            if context.sender_person_id
            else {}
        )
        references: list[EntityReference] = []
        seen = {context.sender_person_id}

        for target in message.meta.get("at_user_ids", []):
            if message.to_ai and str(target) == message.at_user_id:
                continue
            result = await self.resolve_people(context, str(target), 2)
            references.append(self._mention_from_result(f"@{target}", "explicit_at", result))
            for candidate in result["candidates"][:1]:
                seen.add(candidate["person_id"])

        if message.quote_ref and message.quote_ref.sender.user_id:
            result = await self.resolve_people(context, message.quote_ref.sender.user_id, 2)
            references.append(self._mention_from_result("引用消息发送者", "reply_to", result))

        text = message.text or ""
        matched_roles: list[str] = []
        for role_name in sorted(_ROLE_NAMES, key=len, reverse=True):
            if role_name not in text:
                continue
            if any(role_name in existing for existing in matched_roles):
                continue
            result = await self.resolve_people(context, role_name, 3)
            references.append(self._mention_from_result(role_name, "group_role", result))
            matched_roles.append(role_name)

        name_rows = await self._db.fetch(
            "SELECT gm.person_id::text,COALESCE(NULLIF(gm.group_card,''),NULLIF(gm.nickname,''),'') AS name "
            "FROM group_members gm WHERE gm.platform=$1 AND gm.account_id=$2 AND gm.chat_id=$3 "
            "AND gm.is_active AND (length(gm.group_card)>=2 OR length(gm.nickname)>=2)",
            context.platform,
            context.account_id,
            context.chat_id,
        )
        matched_names: dict[str, list[str]] = {}
        for row in name_rows:
            name = str(row["name"] or "")
            if name and name in text:
                matched_names.setdefault(name, []).append(str(row["person_id"]))
        selected_names: list[str] = []
        for name in sorted(matched_names, key=len, reverse=True):
            if any(name in existing for existing in selected_names):
                continue
            selected_names.append(name)
            person_ids = matched_names[name]
            unique_ids = tuple(dict.fromkeys(person_ids))
            if len(unique_ids) == 1 and unique_ids[0] not in seen:
                references.append(
                    EntityReference(
                        text=name,
                        status="resolved",
                        person_id=unique_ids[0],
                        evidence=({"type": "group_card_match", "name": name},),
                    )
                )
                seen.add(unique_ids[0])
            elif len(unique_ids) > 1:
                references.append(
                    EntityReference(
                        text=name,
                        status="candidate",
                        candidates=tuple(
                            EntityCandidate(person_id=person_id, confidence=0.7)
                            for person_id in unique_ids
                        ),
                    )
                )
        participants = await self._recent_participants(
            context,
            recent_participants_limit,
            recent_lookback_sec,
        )
        if context.sender_person_id and all(
            item["person_id"] != context.sender_person_id for item in participants
        ):
            participants = (
                {
                    "person_id": context.sender_person_id,
                    "display_name": message.sender.name or "",
                    "group_card": "",
                    "roles": [],
                    "last_message_id": "",
                    "last_seen_at": "now",
                },
            ) + participants
        return EntityContext(
            current_sender=sender,
            references=tuple(references),
            recent_participants=participants,
        )

    # 读取会话近期发言者快照
    async def _recent_participants(
        self,
        context: ToolExecutionContext,
        limit: int,
        lookback_sec: int,
    ) -> tuple[dict, ...]:
        if not context.conversation_id or not context.ai_id:
            return ()
        rows = await self._db.fetch(
            "SELECT pi.person_id::text AS person_id,"
            "COALESCE(NULLIF(gm.group_card,''),NULLIF(gm.nickname,''),NULLIF(p.display_name,''),'') AS display_name,"
            "NULLIF(gm.group_card,'') AS group_card, gm.role AS role, "
            "MAX(m.message_id)::text AS last_message_id, MAX(m.occurred_at) AS last_seen_at "
            "FROM messages m "
            "JOIN platform_identities pi ON pi.identity_id=m.platform_identity_id "
            "JOIN persons p ON p.person_id=pi.person_id "
            "LEFT JOIN group_members gm ON gm.person_id=pi.person_id AND gm.platform=$2 "
            "AND gm.account_id=$3 AND gm.chat_id=$4 AND gm.is_active "
            "WHERE m.conversation_id=$1::uuid AND m.ai_id=$5 AND m.role='user' "
            "AND m.occurred_at>=now()-($6::text || ' seconds')::interval "
            "GROUP BY pi.person_id,p.display_name,gm.group_card,gm.nickname,gm.role "
            "ORDER BY last_seen_at DESC LIMIT $7",
            context.conversation_id,
            context.platform,
            context.account_id,
            context.chat_id,
            context.ai_id,
            str(int(lookback_sec)),
            int(limit),
        )
        return tuple(
            {
                "person_id": row["person_id"],
                "display_name": row["display_name"] or "",
                "group_card": row["group_card"] or "",
                "roles": [row["role"]] if row["role"] else [],
                "last_message_id": row["last_message_id"] or "",
                "last_seen_at": str(row["last_seen_at"]),
            }
            for row in rows
        )

    async def search_group_history(
        self,
        context: ToolExecutionContext,
        query: str,
        limit: int,
        lookback_sec: int,
    ) -> list[dict]:
        pattern = f"%{query.strip()}%"
        rows = await self._db.fetch(
            "SELECT m.message_id::text,m.role,m.content,m.occurred_at,"
            "pi.person_id::text AS person_id,COALESCE(NULLIF(gm.group_card,''),"
            "NULLIF(gm.nickname,''),NULLIF(p.display_name,''),'') AS display_name "
            "FROM messages m "
            "LEFT JOIN platform_identities pi ON pi.identity_id=m.platform_identity_id "
            "LEFT JOIN persons p ON p.person_id=pi.person_id "
            "LEFT JOIN group_members gm ON gm.person_id=pi.person_id AND gm.platform=$3 "
            "AND gm.account_id=$4 AND gm.chat_id=$5 "
            "WHERE m.conversation_id=$1::uuid AND m.ai_id=$2 "
            "AND m.occurred_at>=now()-($6::text || ' seconds')::interval "
            "AND ($7='' OR COALESCE(m.content->>'text','') ILIKE $8) "
            "ORDER BY m.occurred_at DESC LIMIT $9",
            context.conversation_id,
            context.ai_id,
            context.platform,
            context.account_id,
            context.chat_id,
            str(lookback_sec),
            query.strip(),
            pattern,
            limit,
        )
        return [
            {
                "message_id": row["message_id"],
                "sender": {
                    "person_id": row["person_id"],
                    "display_name": row["display_name"] or ("AI" if row["role"] == "assistant" else ""),
                    "role": row["role"],
                },
                "text": self._message_text(row["content"]),
                "occurred_at": str(row["occurred_at"]),
            }
            for row in rows
        ]

    @staticmethod
    def _message_text(content) -> str:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return content
        return str((content or {}).get("text") or "")

    @staticmethod
    def _add_candidate(
        candidates: dict[str, dict],
        person_id: str,
        display_name: str,
        confidence: float,
        evidence: dict,
    ) -> None:
        item = candidates.setdefault(
            str(person_id),
            {
                "person_id": str(person_id),
                "display_name": str(display_name or ""),
                "confidence": 0.0,
                "evidence": [],
            },
        )
        item["confidence"] = max(float(item["confidence"]), confidence)
        item["evidence"].append(evidence)

    @staticmethod
    def _mention_from_result(text: str, resolution_type: str, result: dict) -> EntityReference:
        raw = list(result.get("candidates") or [])
        candidates = tuple(
            EntityCandidate(
                person_id=str(item.get("person_id") or ""),
                display_name=str(item.get("display_name") or ""),
                confidence=float(item.get("confidence") or 0.0),
                evidence=tuple(item.get("evidence") or []),
            )
            for item in raw
            if item.get("person_id")
        )
        if len(candidates) == 1 and candidates[0].confidence >= 0.9:
            return EntityReference(
                text=text,
                status="resolved",
                person_id=candidates[0].person_id,
                display_name=candidates[0].display_name,
                evidence=({"type": resolution_type},),
            )
        if candidates:
            return EntityReference(text=text, status="candidate", candidates=candidates)
        return EntityReference(text=text, status="unresolved")
