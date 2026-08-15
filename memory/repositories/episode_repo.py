from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.contracts.tools import ToolExecutionContext
from shared.infrastructure import models as m
from shared.infrastructure.snowflake import new_snowflake_id


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
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(func.max(m.ConversationEpisode.ended_at).label("last_ended_at")).where(
                        m.ConversationEpisode.ai_id == ai_id,
                        m.ConversationEpisode.person_id == int(person_id),
                        m.ConversationEpisode.conversation_id == int(conversation_id),
                    )
                )
            ).first()
            last_ended_at = row.last_ended_at if row else None
            conditions = [
                m.Message.ai_id == ai_id,
                m.Message.conversation_id == int(conversation_id),
                m.Message.occurred_at
                <= datetime.fromtimestamp(float(ended_at), tz=timezone.utc),
                or_(
                    m.Message.role == "assistant",
                    m.PlatformIdentity.person_id == int(person_id),
                ),
            ]
            if last_ended_at is not None:
                conditions.append(m.Message.occurred_at > last_ended_at)
            rows = await session.execute(
                select(
                    m.Message.message_id,
                    m.Message.role,
                    m.Message.content,
                    func.extract("epoch", m.Message.occurred_at).label("occurred_at"),
                    func.coalesce(m.Person.display_name, m.PlatformIdentity.platform_user_id, "").label(
                        "speaker"
                    ),
                    m.PlatformIdentity.person_id.label("person_id"),
                )
                .select_from(m.Message)
                .outerjoin(
                    m.PlatformIdentity,
                    m.PlatformIdentity.identity_id == m.Message.platform_identity_id,
                )
                .outerjoin(m.Person, m.Person.person_id == m.PlatformIdentity.person_id)
                .where(*conditions)
                .order_by(m.Message.occurred_at, m.Message.message_id)
            )
        result = []
        for item in rows:
            content = item.content if isinstance(item.content, dict) else json.loads(item.content)
            text = str(content.get("text") or content.get("media_desc") or "").strip()
            if not text:
                continue
            result.append(
                EpisodeMessage(
                    message_id=str(item.message_id),
                    role=item.role,
                    speaker=item.speaker or "AI",
                    person_id=str(item.person_id) if item.person_id else "",
                    text=text,
                    occurred_at=float(item.occurred_at),
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
        async with self._db.session() as session:
            async with session.begin():
                existing = (
                    await session.execute(
                        select(m.ConversationEpisode.episode_id).where(
                            m.ConversationEpisode.activity_id == activity_id
                        )
                    )
                ).first()
                if existing:
                    return await self._existing_extraction(session, existing.episode_id)
                episode_id = int(new_snowflake_id())
                session.add(
                    m.ConversationEpisode(
                        episode_id=episode_id,
                        activity_id=activity_id,
                        ai_id=ai_id,
                        person_id=int(person_id),
                        conversation_id=int(conversation_id),
                        started_at=datetime.fromtimestamp(
                            messages[0].occurred_at, tz=timezone.utc
                        ),
                        ended_at=datetime.fromtimestamp(
                            messages[-1].occurred_at, tz=timezone.utc
                        ),
                        summary=summary,
                        source_message_ids=[int(item.message_id) for item in messages],
                        estimated_tokens=estimated_tokens,
                    )
                )
                atom_ids_by_owner: dict[tuple[str, str], list[str]] = {}
                for atom in atoms:
                    atom_id = int(new_snowflake_id())
                    owner_type = str(atom["owner_type"])
                    owner_id = ai_id if owner_type == "self" else person_id
                    session.add(
                        m.MemoryAtom(
                            atom_id=atom_id,
                            ai_id=ai_id,
                            owner_type=owner_type,
                            owner_id=owner_id,
                            person_id=int(person_id),
                            episode_id=episode_id,
                            memory_type=atom["type"],
                            content=atom["content"],
                            importance=atom["importance"],
                            confidence=atom["confidence"],
                            source_message_ids=[int(item.message_id) for item in messages],
                        )
                    )
                    atom_ids_by_owner.setdefault((owner_type, owner_id), []).append(
                        str(atom_id)
                    )
                await self._refresh_conversation_summary(session, ai_id, conversation_id)
                return ExtractionRecord(str(episode_id), atom_ids_by_owner)

    # 查找已有记忆提取记录
    async def _existing_extraction(self, session, episode_id: int) -> ExtractionRecord:
        rows = await session.execute(
            select(m.MemoryAtom.atom_id, m.MemoryAtom.owner_type, m.MemoryAtom.owner_id).where(
                m.MemoryAtom.episode_id == episode_id
            )
        )
        atoms: dict[tuple[str, str], list[str]] = {}
        for row in rows:
            atoms.setdefault((row.owner_type, row.owner_id), []).append(str(row.atom_id))
        return ExtractionRecord(str(episode_id), atoms)

    # 刷新会话摘要
    async def _refresh_conversation_summary(
        self, session, ai_id: str, conversation_id: str
    ) -> None:
        rows = await session.execute(
            select(m.ConversationEpisode.summary)
            .where(
                m.ConversationEpisode.ai_id == ai_id,
                m.ConversationEpisode.conversation_id == int(conversation_id),
            )
            .order_by(m.ConversationEpisode.ended_at.desc())
            .limit(self._history_episode_limit)
        )
        summary = "\n".join(row.summary for row in reversed(list(rows)) if row.summary.strip())
        stmt = (
            pg_insert(m.ConversationSummary)
            .values(ai_id=ai_id, conversation_id=int(conversation_id), summary=summary, version=1)
            .on_conflict_do_update(
                index_elements=[m.ConversationSummary.ai_id, m.ConversationSummary.conversation_id],
                set_={
                    "summary": summary,
                    "version": m.ConversationSummary.version + 1,
                    "updated_at": func.now(),
                },
            )
        )
        await session.execute(stmt)

    # 获取记忆上下文
    async def context(self, ai_id: str, person_id: str, conversation_id: str) -> dict:
        async with self._db.session() as session:
            self_row = (
                await session.execute(
                    select(m.MemoryDocument.markdown_content, m.MemoryDocument.version).where(
                        m.MemoryDocument.ai_id == ai_id,
                        m.MemoryDocument.owner_type == "self",
                        m.MemoryDocument.owner_id == ai_id,
                    )
                )
            ).first()
            person_row = None
            if person_id:
                person_row = (
                    await session.execute(
                        select(m.MemoryDocument.markdown_content, m.MemoryDocument.version).where(
                            m.MemoryDocument.ai_id == ai_id,
                            m.MemoryDocument.owner_type == "person",
                            m.MemoryDocument.owner_id == person_id,
                        )
                    )
                ).first()
            summary_row = None
            if conversation_id:
                summary_row = (
                    await session.execute(
                        select(m.ConversationSummary.summary, m.ConversationSummary.version).where(
                            m.ConversationSummary.ai_id == ai_id,
                            m.ConversationSummary.conversation_id == int(conversation_id),
                        )
                    )
                ).first()
            return {
                "self_markdown": self_row.markdown_content if self_row else "",
                "person_markdown": person_row.markdown_content if person_row else "",
                "conversation_summary": summary_row.summary if summary_row else "",
            }

    # 按当前会话投影人物事实
    async def person_context(
        self,
        context: ToolExecutionContext,
        person_id: str,
        fact_limit: int,
    ) -> dict | None:
        async with self._db.session() as session:
            conversation = (
                await session.execute(
                    select(
                        select(m.Conversation.conversation_id)
                        .where(
                            m.Conversation.conversation_id == int(context.conversation_id),
                            m.Conversation.platform == context.platform,
                            m.Conversation.account_id == context.account_id,
                            m.Conversation.platform_chat_id == context.chat_id,
                            m.Conversation.chat_type == context.chat_type,
                        )
                        .exists()
                    )
                )
            ).first()
            has_messages = (
                await session.execute(
                    select(
                        select(m.Message.message_id)
                        .where(
                            m.Message.conversation_id == int(context.conversation_id),
                            m.Message.ai_id == context.ai_id,
                        )
                        .exists()
                    )
                )
            ).first()
            if conversation is None or not conversation[0] or not has_messages[0]:
                return None
            if context.chat_type == "group":
                allowed = (
                    await session.execute(
                        select(
                            select(m.GroupMember.person_id)
                            .where(
                                m.GroupMember.platform == context.platform,
                                m.GroupMember.account_id == context.account_id,
                                m.GroupMember.chat_id == context.chat_id,
                                m.GroupMember.person_id == int(person_id),
                                m.GroupMember.is_active.is_(True),
                            )
                            .exists()
                        )
                    )
                ).first()
                if allowed is None or not allowed[0]:
                    return None
            elif context.chat_type == "private":
                if person_id != context.sender_person_id:
                    return None
            else:
                return None

            rows = await session.execute(
                select(
                    m.MemoryAtom.content,
                    m.MemoryAtom.memory_type,
                    m.MemoryAtom.importance,
                    m.MemoryAtom.confidence,
                    m.MemoryAtom.created_at,
                )
                .select_from(m.MemoryAtom)
                .join(
                    m.ConversationEpisode,
                    m.ConversationEpisode.episode_id == m.MemoryAtom.episode_id,
                )
                .where(
                    m.MemoryAtom.ai_id == context.ai_id,
                    m.MemoryAtom.owner_type == "person",
                    m.MemoryAtom.owner_id == person_id,
                    m.ConversationEpisode.conversation_id == int(context.conversation_id),
                )
                .order_by(
                    m.MemoryAtom.importance.desc(),
                    m.MemoryAtom.confidence.desc(),
                    m.MemoryAtom.created_at.desc(),
                )
                .limit(int(fact_limit))
            )
            summary = (
                await session.execute(
                    select(m.ConversationSummary.summary).where(
                        m.ConversationSummary.ai_id == context.ai_id,
                        m.ConversationSummary.conversation_id == int(context.conversation_id),
                    )
                )
            ).first()
            return {
                "person_id": person_id,
                "scene": context.chat_type,
                "facts": [
                    {
                        "content": row.content,
                        "type": row.memory_type,
                        "importance": float(row.importance),
                        "confidence": float(row.confidence),
                    }
                    for row in rows
                ],
                "conversation_summary": summary.summary if summary else "",
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
        async with self._db.session() as session:
            document_row = (
                await session.execute(
                    select(m.MemoryDocument.markdown_content, m.MemoryDocument.version).where(
                        m.MemoryDocument.ai_id == ai_id,
                        m.MemoryDocument.owner_type == owner_type,
                        m.MemoryDocument.owner_id == owner_id,
                    )
                )
            ).first()
            atom_rows = await session.execute(
                select(
                    m.MemoryAtom.atom_id,
                    m.MemoryAtom.memory_type,
                    m.MemoryAtom.content,
                    m.MemoryAtom.importance,
                    m.MemoryAtom.confidence,
                )
                .where(
                    m.MemoryAtom.ai_id == ai_id,
                    m.MemoryAtom.atom_id.in_([int(item) for item in atom_ids]),
                )
                .order_by(m.MemoryAtom.created_at, m.MemoryAtom.atom_id)
            )
            episode_rows = await session.execute(
                select(m.ConversationEpisode.summary)
                .where(
                    m.ConversationEpisode.ai_id == ai_id,
                    m.ConversationEpisode.episode_id.in_(
                        [int(item) for item in episode_ids]
                    ),
                )
                .order_by(m.ConversationEpisode.ended_at, m.ConversationEpisode.episode_id)
            )
            document = MemoryDocument(
                markdown=document_row.markdown_content if document_row else "",
                version=int(document_row.version) if document_row else 0,
            )
            return (
                document,
                [
                    {
                        "atom_id": str(row.atom_id),
                        "memory_type": row.memory_type,
                        "content": row.content,
                        "importance": float(row.importance),
                        "confidence": float(row.confidence),
                    }
                    for row in atom_rows
                ],
                [row.summary for row in episode_rows],
            )

    # 保存文档
    async def save_document(
        self,
        ai_id: str,
        owner_type: str,
        owner_id: str,
        markdown: str,
        expected_version: int,
    ) -> int:
        async with self._db.session() as session:
            if expected_version == 0:
                stmt = (
                    pg_insert(m.MemoryDocument)
                    .values(
                        ai_id=ai_id,
                        owner_type=owner_type,
                        owner_id=owner_id,
                        markdown_content=markdown,
                        version=1,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            m.MemoryDocument.ai_id,
                            m.MemoryDocument.owner_type,
                            m.MemoryDocument.owner_id,
                        ]
                    )
                    .returning(m.MemoryDocument.version)
                )
                row = (await session.execute(stmt)).first()
            else:
                row = (
                    await session.execute(
                        update(m.MemoryDocument)
                        .where(
                            m.MemoryDocument.ai_id == ai_id,
                            m.MemoryDocument.owner_type == owner_type,
                            m.MemoryDocument.owner_id == owner_id,
                            m.MemoryDocument.version == int(expected_version),
                        )
                        .values(
                            markdown_content=markdown,
                            version=m.MemoryDocument.version + 1,
                            updated_at=func.now(),
                        )
                        .returning(m.MemoryDocument.version)
                    )
                ).first()
            await session.commit()
        if row is None:
            raise RuntimeError("长期记忆文档版本冲突")
        return int(row.version)
