from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from shared.contracts.tools import ToolExecutionContext


# 表示会话片段消息数据
@dataclass(frozen=True)
class EpisodeMessage:
    message_id: str
    role: str
    speaker: str
    person_id: str
    text: str
    occurred_at: float


# 表示记忆文档数据
@dataclass(frozen=True)
class MemoryDocument:
    markdown: str
    version: int


# 表示记忆提取记录数据
@dataclass(frozen=True)
class ExtractionRecord:
    episode_id: str
    atom_ids_by_owner: dict[tuple[str, str], list[str]]


# 管理会话片段记忆存储库持久化
class EpisodeMemoryRepository:
    """持久化会话片段、原子记忆和长期 Markdown"""

    # 初始化当前实例
    def __init__(self, db, history_episode_limit: int) -> None:
        self._db = db
        self._history_episode_limit = int(history_episode_limit)

    # 加载会话片段消息列表
    async def load_episode_messages(
        self,
        ai_id: str,
        person_id: str,
        conversation_id: str,
        ended_at: float,
    ) -> list[EpisodeMessage]:
        row = await self._db.fetchrow(
            "SELECT max(ended_at) AS last_ended_at FROM conversation_episodes "
            "WHERE ai_id=$1 AND person_id=$2::uuid AND conversation_id=$3::uuid",
            ai_id,
            person_id,
            conversation_id,
        )
        last_ended_at = row["last_ended_at"] if row else None
        rows = await self._db.fetch(
            "SELECT m.message_id::text, m.role, m.content, extract(epoch from m.occurred_at) AS occurred_at, "
            "coalesce(p.display_name, pi.platform_user_id, '') AS speaker, "
            "pi.person_id::text AS person_id "
            "FROM messages m "
            "LEFT JOIN platform_identities pi ON pi.identity_id=m.platform_identity_id "
            "LEFT JOIN persons p ON p.person_id=pi.person_id "
            "WHERE m.ai_id=$1 AND m.conversation_id=$2::uuid "
            "AND ($3::timestamptz IS NULL OR m.occurred_at>$3::timestamptz) "
            "AND m.occurred_at<=to_timestamp($4) "
            "AND (m.role='assistant' OR pi.person_id=$5::uuid) "
            "ORDER BY m.occurred_at, m.message_id",
            ai_id,
            conversation_id,
            last_ended_at,
            ended_at,
            person_id,
        )
        result = []
        for item in rows:
            content = item["content"] if isinstance(item["content"], dict) else json.loads(item["content"])
            text = str(content.get("text") or content.get("media_desc") or "").strip()
            if not text:
                continue
            result.append(
                EpisodeMessage(
                    message_id=item["message_id"],
                    role=item["role"],
                    speaker=item["speaker"] or "AI",
                    person_id=item["person_id"] or "",
                    text=text,
                    occurred_at=float(item["occurred_at"]),
                )
            )
        return result

    # 保存记忆提取
    async def save_extraction(
        self,
        *,
        activity_id: str,
        ai_id: str,
        person_id: str,
        conversation_id: str,
        messages: list[EpisodeMessage],
        summary: str,
        atoms: list[dict],
        estimated_tokens: int,
    ) -> ExtractionRecord:
        async with self._db.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT episode_id::text FROM conversation_episodes WHERE activity_id=$1",
                    activity_id,
                )
                if existing:
                    return await self._existing_extraction(conn, existing["episode_id"])
                episode_id = str(uuid.uuid4())
                await conn.execute(
                    "INSERT INTO conversation_episodes(episode_id,activity_id,ai_id,person_id,conversation_id,"
                    "started_at,ended_at,summary,source_message_ids,estimated_tokens) "
                    "VALUES($1::uuid,$2,$3,$4::uuid,$5::uuid,to_timestamp($6),to_timestamp($7),$8,$9::uuid[],$10)",
                    episode_id,
                    activity_id,
                    ai_id,
                    person_id,
                    conversation_id,
                    messages[0].occurred_at,
                    messages[-1].occurred_at,
                    summary,
                    [uuid.UUID(item.message_id) for item in messages],
                    estimated_tokens,
                )
                atom_ids_by_owner: dict[tuple[str, str], list[str]] = {}
                for atom in atoms:
                    atom_id = str(uuid.uuid4())
                    owner_type = str(atom["owner_type"])
                    owner_id = ai_id if owner_type == "self" else person_id
                    await conn.execute(
                        "INSERT INTO memory_atoms(atom_id,ai_id,owner_type,owner_id,person_id,episode_id,"
                        "memory_type,content,importance,confidence,source_message_ids) "
                        "VALUES($1::uuid,$2,$3,$4,$5::uuid,$6::uuid,$7,$8,$9,$10,$11::uuid[])",
                        atom_id,
                        ai_id,
                        owner_type,
                        owner_id,
                        person_id,
                        episode_id,
                        atom["type"],
                        atom["content"],
                        atom["importance"],
                        atom["confidence"],
                        [uuid.UUID(item.message_id) for item in messages],
                    )
                    atom_ids_by_owner.setdefault((owner_type, owner_id), []).append(atom_id)
                await self._refresh_conversation_summary(conn, ai_id, conversation_id)
                return ExtractionRecord(episode_id, atom_ids_by_owner)

    # 查找已有记忆提取记录
    async def _existing_extraction(self, conn, episode_id: str) -> ExtractionRecord:
        rows = await conn.fetch(
            "SELECT atom_id::text, owner_type, owner_id FROM memory_atoms WHERE episode_id=$1::uuid",
            episode_id,
        )
        atoms: dict[tuple[str, str], list[str]] = {}
        for row in rows:
            atoms.setdefault((row["owner_type"], row["owner_id"]), []).append(row["atom_id"])
        return ExtractionRecord(episode_id, atoms)

    # 刷新会话摘要
    async def _refresh_conversation_summary(self, conn, ai_id: str, conversation_id: str) -> None:
        rows = await conn.fetch(
            "SELECT summary FROM conversation_episodes WHERE ai_id=$1 AND conversation_id=$2::uuid "
            "ORDER BY ended_at DESC LIMIT $3",
            ai_id,
            conversation_id,
            self._history_episode_limit,
        )
        summary = "\n".join(row["summary"] for row in reversed(rows) if row["summary"].strip())
        await conn.execute(
            "INSERT INTO conversation_summaries(ai_id,conversation_id,summary,version,updated_at) "
            "VALUES($1,$2::uuid,$3,1,now()) ON CONFLICT(ai_id,conversation_id) DO UPDATE SET "
            "summary=EXCLUDED.summary,version=conversation_summaries.version+1,updated_at=now()",
            ai_id,
            conversation_id,
            summary,
        )

    # 获取记忆上下文
    async def context(self, ai_id: str, person_id: str, conversation_id: str) -> dict:
        self_row = await self._db.fetchrow(
            "SELECT markdown_content,version FROM memory_documents "
            "WHERE ai_id=$1 AND owner_type='self' AND owner_id=$1",
            ai_id,
        )
        person_row = None
        if person_id:
            person_row = await self._db.fetchrow(
                "SELECT markdown_content,version FROM memory_documents "
                "WHERE ai_id=$1 AND owner_type='person' AND owner_id=$2",
                ai_id,
                person_id,
            )
        summary_row = None
        if conversation_id:
            summary_row = await self._db.fetchrow(
                "SELECT summary,version FROM conversation_summaries "
                "WHERE ai_id=$1 AND conversation_id=$2::uuid",
                ai_id,
                conversation_id,
            )
        return {
            "self_markdown": self_row["markdown_content"] if self_row else "",
            "person_markdown": person_row["markdown_content"] if person_row else "",
            "conversation_summary": summary_row["summary"] if summary_row else "",
        }

    # 按当前会话投影人物事实
    async def person_context(
        self,
        context: ToolExecutionContext,
        person_id: str,
        fact_limit: int,
    ) -> dict | None:
        conversation = await self._db.fetchrow(
            "SELECT EXISTS(SELECT 1 FROM conversations c WHERE c.conversation_id=$1::uuid "
            "AND c.platform=$2 AND c.account_id=$3 AND c.platform_chat_id=$4 AND c.chat_type=$5 "
            "AND EXISTS(SELECT 1 FROM messages m WHERE m.conversation_id=c.conversation_id "
            "AND m.ai_id=$6)) AS exists",
            context.conversation_id,
            context.platform,
            context.account_id,
            context.chat_id,
            context.chat_type,
            context.ai_id,
        )
        if conversation is None or not conversation["exists"]:
            return None
        if context.chat_type == "group":
            allowed = await self._db.fetchrow(
                "SELECT EXISTS(SELECT 1 FROM group_members gm WHERE gm.platform=$1 "
                "AND gm.account_id=$2 AND gm.chat_id=$3 AND gm.person_id=$4::uuid "
                "AND gm.is_active) AS exists",
                context.platform,
                context.account_id,
                context.chat_id,
                person_id,
            )
            if allowed is None or not allowed["exists"]:
                return None
        elif context.chat_type == "private":
            if person_id != context.sender_person_id:
                return None
        else:
            return None

        rows = await self._db.fetch(
            "SELECT ma.content,ma.memory_type,ma.importance,ma.confidence,ma.created_at "
            "FROM memory_atoms ma JOIN conversation_episodes ce ON ce.episode_id=ma.episode_id "
            "WHERE ma.ai_id=$1 AND ma.owner_type='person' AND ma.owner_id=$2 "
            "AND ce.conversation_id=$3::uuid "
            "ORDER BY ma.importance DESC,ma.confidence DESC,ma.created_at DESC LIMIT $4",
            context.ai_id,
            person_id,
            context.conversation_id,
            fact_limit,
        )
        summary = await self._db.fetchrow(
            "SELECT summary FROM conversation_summaries WHERE ai_id=$1 AND conversation_id=$2::uuid",
            context.ai_id,
            context.conversation_id,
        )
        return {
            "person_id": person_id,
            "scene": context.chat_type,
            "facts": [
                {
                    "content": row["content"],
                    "type": row["memory_type"],
                    "importance": float(row["importance"]),
                    "confidence": float(row["confidence"]),
                }
                for row in rows
            ],
            "conversation_summary": summary["summary"] if summary else "",
        }

    # 生成记忆聚合输入
    async def consolidation_input(
        self,
        ai_id: str,
        owner_type: str,
        owner_id: str,
        episode_ids: list[str],
        atom_ids: list[str],
    ) -> tuple[MemoryDocument, list[dict], list[str]]:
        document_row = await self._db.fetchrow(
            "SELECT markdown_content,version FROM memory_documents "
            "WHERE ai_id=$1 AND owner_type=$2 AND owner_id=$3",
            ai_id,
            owner_type,
            owner_id,
        )
        atom_rows = await self._db.fetch(
            "SELECT atom_id::text,memory_type,content,importance,confidence "
            "FROM memory_atoms WHERE ai_id=$1 AND atom_id=ANY($2::uuid[]) ORDER BY created_at,atom_id",
            ai_id,
            [uuid.UUID(item) for item in atom_ids],
        )
        episode_rows = await self._db.fetch(
            "SELECT summary FROM conversation_episodes WHERE ai_id=$1 "
            "AND episode_id=ANY($2::uuid[]) ORDER BY ended_at,episode_id",
            ai_id,
            [uuid.UUID(item) for item in episode_ids],
        )
        document = MemoryDocument(
            markdown=document_row["markdown_content"] if document_row else "",
            version=int(document_row["version"]) if document_row else 0,
        )
        return document, [dict(row) for row in atom_rows], [row["summary"] for row in episode_rows]

    # 保存文档
    async def save_document(
        self,
        ai_id: str,
        owner_type: str,
        owner_id: str,
        markdown: str,
        expected_version: int,
    ) -> int:
        if expected_version == 0:
            row = await self._db.fetchrow(
                "INSERT INTO memory_documents(ai_id,owner_type,owner_id,markdown_content,version,updated_at) "
                "VALUES($1,$2,$3,$4,1,now()) ON CONFLICT(ai_id,owner_type,owner_id) DO NOTHING "
                "RETURNING version",
                ai_id,
                owner_type,
                owner_id,
                markdown,
            )
        else:
            row = await self._db.fetchrow(
                "UPDATE memory_documents SET markdown_content=$4,version=version+1,updated_at=now() "
                "WHERE ai_id=$1 AND owner_type=$2 AND owner_id=$3 AND version=$5 RETURNING version",
                ai_id,
                owner_type,
                owner_id,
                markdown,
                expected_version,
            )
        if row is None:
            raise RuntimeError("长期记忆文档版本冲突")
        return int(row["version"])
