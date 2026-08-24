from __future__ import annotations

import logging
import time
from pathlib import Path

from memory.repositories.postgres_memory_repository import PostgresMemoryRepository
from memory.services.sticker_service import StickerService

logger = logging.getLogger("ailove.memory.cleanup")


class MemoryCleanupService:
    def __init__(
        self,
        stickers: StickerService,
        memories: PostgresMemoryRepository,
        data_dir: str,
        file_max_age_sec: float,
    ) -> None:
        self._stickers = stickers
        self._memories = memories
        self._data_dir = data_dir
        self._file_max_age_sec = file_max_age_sec

    async def cleanup(self) -> None:
        removed_stickers = await self._stickers.cleanup()
        memory_result = await self._memories.cleanup()
        removed_files = self._cleanup_files()
        logger.info(
            "[memory] 每日清理（表情 %s 个，记忆休眠 %s 个，记忆删除 %s 个，过期文件 %s 个）",
            removed_stickers,
            memory_result["dormant"],
            memory_result["deleted"],
            removed_files,
        )

    def _cleanup_files(self) -> int:
        cutoff = time.time() - self._file_max_age_sec
        removed = 0
        for path in Path(self._data_dir).rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        return removed
