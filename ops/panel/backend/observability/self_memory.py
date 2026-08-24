from __future__ import annotations

from sqlalchemy import select

from shared.persistence import database_models as m

from .schemas import MemoryDocumentResponse, SelfMemoryResponse


class SelfMemoryReader:
    """只负责读取 AI 自身的长期记忆文档。"""

    def __init__(self, database) -> None:
        self._database = database

    async def read(self, ai_id: str) -> SelfMemoryResponse:
        async with self._database.session() as session:
            result = await session.execute(
                select(
                    m.MemoryDocument.markdown_content,
                    m.MemoryDocument.version,
                    m.MemoryDocument.updated_at,
                ).where(
                    m.MemoryDocument.ai_id == ai_id,
                    m.MemoryDocument.owner_type == "self",
                    m.MemoryDocument.owner_id == ai_id,
                )
            )
            row = result.one_or_none()
        memory = None
        if row is not None:
            memory = MemoryDocumentResponse(
                markdown=row.markdown_content,
                version=row.version,
                updated_at=row.updated_at,
            )
        return SelfMemoryResponse(ai_id=ai_id, memory=memory)
