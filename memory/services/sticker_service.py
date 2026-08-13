
from __future__ import annotations

import re

from memory.repositories.sticker_repo import StickerRepo


class StickerService:

    def __init__(self, gcfg) -> None:
        self._gcfg = gcfg
        self._config = gcfg.section("sticker")
        self._repos: dict[str, StickerRepo] = {}

    def _repo(self, ai_id: str) -> StickerRepo:
        if ai_id not in self._repos:
            repo = StickerRepo(
                ai_id=ai_id,
                data_dir="/app/data/stickers",
                config=self._config,
            )
            repo.delete_unusable(self._collect_min_quality)
            self._repos[ai_id] = repo
        return self._repos[ai_id]

    @property
    def _capacity(self) -> int:
        return int(self._gcfg.get("sticker", "capacity"))

    @property
    def _boost_delta(self) -> float:
        return float(self._gcfg.get("sticker", "boost_delta"))

    @property
    def _threshold(self) -> float:
        return float(self._gcfg.get("sticker", "threshold"))

    @property
    def _collect_min_quality(self) -> float:
        return float(self._gcfg.get("sticker", "collect_min_quality"))

    def add(self, ai_id: str, data: dict) -> dict:
        repo = self._repo(ai_id)
        sid = data.get("id", "")
        if float(data.get("match_quality", 0.0)) < self._collect_min_quality or not data.get("description"):
            return {"ok": True, "action": "ignored"}
        if repo.exists(sid):
            return {"ok": True, "action": "exists"}
        if repo.count() >= self._capacity:
            evicted = repo.delete_lowest()
            repo.insert(data)
            return {"ok": True, "action": "evict", "evicted": evicted}
        repo.insert(data)
        return {"ok": True, "action": "add"}

    def search(self, ai_id: str, query: str) -> dict | None:
        stickers = self._repo(ai_id).all()
        if not stickers:
            return None
        q_tokens = set(_tokenize(query))
        scored = []
        for s in stickers:
            desc_tokens = set(_tokenize(s.get("description", ""))) | set(_tokenize(" ".join(s.get("tags", []))))
            overlap = len(q_tokens & desc_tokens)
            score = (
                overlap * float(self._config["search_weights"]["token_overlap"])
                + float(s["match_quality"]) * float(self._config["search_weights"]["match_quality"])
                + float(s["usage_strength"]) * float(self._config["search_weights"]["usage_strength"])
                + float(s["freshness"]) * float(self._config["search_weights"]["freshness"])
            )
            scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        if not scored or len(q_tokens & (
            set(_tokenize(scored[0][1].get("description", "")))
            | set(_tokenize(" ".join(scored[0][1].get("tags", []))))
        )) == 0:
            return None
        return scored[0][1]

    def list(self, ai_id: str, top_k: int) -> list[dict]:
        stickers = self._repo(ai_id).all()
        stickers.sort(key=lambda s: -s.get("retention_score", 0.0))
        return stickers[:top_k]

    @property
    def list_limit(self) -> int:
        return int(self._config["list_limit"])

    def boost(self, ai_id: str, sticker_id: str) -> None:
        self._repo(ai_id).boost(sticker_id, self._boost_delta)

    def cleanup(self) -> int:
        return sum(repo.cleanup(self._threshold) for repo in self._repos.values())

    def close(self) -> None:
        for repo in self._repos.values():
            repo.close()
        self._repos.clear()


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop_chars = set("的一了是在我你他她它和就都也很还啊呀呢吧吗哦嗯这那有被把与及")
    for ch in text:
        if "一" <= ch <= "鿿" and ch not in stop_chars:
            tokens.append(ch)
    return tokens
