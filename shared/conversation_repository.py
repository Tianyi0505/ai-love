from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared import database_models as m
from shared.contracts.rpc.social import SocialSendRequest, SocialSendResponse
from shared.database import Database
from shared.snowflake_id_generator import snowflake_ids


class ConversationRepository:
    def __init__(self, db: Database, retention_days: int) -> None:
        self._db = db
        self._retention_days = retention_days

    async def get_or_create(
        self,
        platform: str,
        account_id: str,
        platform_chat_id: str,
        chat_type: str,
    ) -> str:
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.Conversation)
                .values(
                    conversation_id=snowflake_ids().next_id(),
                    platform=platform,
                    account_id=account_id,
                    platform_chat_id=platform_chat_id,
                    chat_type=chat_type,
                )
                .on_conflict_do_update(
                    index_elements=[
                        m.Conversation.platform,
                        m.Conversation.account_id,
                        m.Conversation.platform_chat_id,
                    ],
                    set_={"chat_type": chat_type},
                )
                .returning(m.Conversation.conversation_id)
            )
            conversation_id = (await session.execute(stmt)).scalar_one()
            await session.commit()
            return str(conversation_id)

    async def record_inbound(self, message, ai_id: str) -> str:
        conversation_id = await self.get_or_create(
            message.platform,
            message.account_id,
            message.chat.chat_id,
            message.chat.chat_type.value,
        )
        platform_message_id = message.message_id
        source_key = (
            f"in:{message.platform}:{message.account_id}:{platform_message_id}" if platform_message_id else None
        )
        occurred_at = datetime.fromtimestamp(message.timestamp, tz=timezone.utc)
        content = {
            "type": message.type.value,
            "text": message.text,
            "media_url": message.media_url,
            "media_desc": message.media_desc,
            "media_urls": message.media_urls,
            "media_descs": message.media_descs,
            "platform_message_id": platform_message_id,
        }
        identity_id = message.meta["platform_identity_id"]
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.Message)
                .values(
                    message_id=snowflake_ids().next_id(),
                    conversation_id=int(conversation_id),
                    ai_id=ai_id,
                    platform_identity_id=int(identity_id),
                    role="user",
                    content=content,
                    occurred_at=occurred_at,
                    retain_until=occurred_at + timedelta(days=self._retention_days),
                    correlation_id=platform_message_id,
                    source_key=source_key,
                )
                .on_conflict_do_nothing(index_elements=[m.Message.source_key])
            )
            await session.execute(stmt)
            await session.commit()
        return conversation_id

    async def record_outbound(
        self,
        request: SocialSendRequest,
        result: SocialSendResponse,
        ai_id: str,
    ) -> str:
        platform = request.channel
        account_id = request.account_id
        conversation_id = await self.get_or_create(
            platform,
            account_id,
            request.chat.chat_id,
            request.chat.chat_type.value,
        )
        platform_message_id = result.message_id
        source_key = f"out:{platform}:{account_id}:{platform_message_id}" if platform_message_id else None
        content = {
            "type": request.type,
            "text": request.text,
            "has_sticker": request.sticker is not None,
            "has_voice": request.voice is not None,
            "platform_message_id": platform_message_id,
        }
        occurred_at = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = (
                pg_insert(m.Message)
                .values(
                    message_id=snowflake_ids().next_id(),
                    conversation_id=int(conversation_id),
                    ai_id=ai_id,
                    role="assistant",
                    content=content,
                    occurred_at=occurred_at,
                    retain_until=occurred_at + timedelta(days=self._retention_days),
                    correlation_id=platform_message_id,
                    source_key=source_key,
                )
                .on_conflict_do_nothing(index_elements=[m.Message.source_key])
            )
            await session.execute(stmt)
            await session.commit()
        return conversation_id
