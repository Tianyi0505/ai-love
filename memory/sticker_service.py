from __future__ import annotations

import math
from datetime import datetime, timezone

import bm25s
import jieba

from memory.sticker_repository import StickerRepository
from shared.global_settings import StickerSettings


class StickerService:
    def __init__(self, repo: StickerRepository, config: StickerSettings) -> None:
        self._repo = repo
        self._settings = config

    def _freshness(self, sticker: dict) -> float:
        anchor = sticker["last_used_at"] or sticker["created_at"]
        elapsed = (datetime.now(timezone.utc) - anchor).total_seconds()
        return math.exp2(-elapsed / self._settings.half_life_sec)

    def _retention_score(self, sticker: dict) -> float:
        weights = self._settings.retention_weights
        return (
            sticker["match_quality"] * weights.match_quality
            + sticker["usage_strength"] * weights.usage_strength
            + self._freshness(sticker) * weights.freshness
        )

    def _present(self, sticker: dict) -> dict:
        return {
            **sticker,
            "freshness": self._freshness(sticker),
            "retention_score": self._retention_score(sticker),
        }

    async def add(self, ai_id: str, data: dict) -> dict:
        if data["match_quality"] < self._settings.collect_min_quality:
            return {"ok": True, "action": "ignored"}
        if await self._repo.exists(ai_id, data["id"]):
            return {"ok": True, "action": "exists"}
        evicted = None
        if await self._repo.count(ai_id) >= self._settings.capacity:
            stickers = await self._repo.all(ai_id)
            lowest = min(stickers, key=self._retention_score)
            await self._repo.delete(ai_id, [lowest["id"]])
            evicted = lowest["description"]
        await self._repo.insert(
            ai_id,
            data,
            self._settings.initial_usage_strength,
            self._settings.initial_boost_count,
        )
        return (
            {"ok": True, "action": "evict", "evicted": evicted}
            if evicted is not None
            else {"ok": True, "action": "add"}
        )

    async def search(self, ai_id: str, query: str) -> dict | None:
        stickers = await self._repo.all(ai_id)
        if not stickers:
            return None
        corpus_tokens = [jieba.lcut(f"{sticker['description']} {' '.join(sticker['tags'])}") for sticker in stickers]
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens, show_progress=False)
        candidate_count = min(self._settings.search_candidate_limit, len(stickers))
        candidates, lexical_scores = retriever.retrieve(
            [jieba.lcut(query)],
            corpus=stickers,
            k=candidate_count,
            show_progress=False,
        )
        weights = self._settings.search_weights
        scored = [
            (
                float(lexical_score) * weights.lexical
                + sticker["match_quality"] * weights.match_quality
                + sticker["usage_strength"] * weights.usage_strength
                + self._freshness(sticker) * weights.freshness,
                sticker,
            )
            for sticker, lexical_score in zip(
                candidates[0],
                lexical_scores[0],
                strict=True,
            )
        ]
        score, sticker = max(scored, key=lambda item: item[0])
        if score < self._settings.search_min_score:
            return None
        return self._present(sticker)

    async def list(self, ai_id: str, top_k: int) -> list[dict]:
        stickers = [self._present(sticker) for sticker in await self._repo.all(ai_id)]
        stickers.sort(key=lambda sticker: -sticker["retention_score"])
        return stickers[:top_k]

    @property
    def list_limit(self) -> int:
        return self._settings.list_limit

    async def boost(self, ai_id: str, sticker_id: str) -> None:
        await self._repo.boost(
            ai_id,
            sticker_id,
            self._settings.boost_delta,
            self._settings.usage_strength_max,
            self._settings.boost_count_increment,
        )

    async def cleanup(self) -> int:
        removed = 0
        for ai_id in await self._repo.list_ai_ids():
            stickers = await self._repo.all(ai_id)
            sticker_ids = [
                sticker["id"] for sticker in stickers if self._retention_score(sticker) < self._settings.threshold
            ]
            if sticker_ids:
                await self._repo.delete(ai_id, sticker_ids)
                removed += len(sticker_ids)
        return removed
