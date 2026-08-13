
from __future__ import annotations

import json


# 处理表情管理请求
class StickerController:

    SUBJECTS = {
        "sticker.add.request": "add",
        "sticker.search.request": "search",
        "sticker.list.request": "list",
        "sticker.boost.request": "boost",
    }

    # 初始化当前实例
    def __init__(self, service) -> None:
        self._service = service

    # 处理事件
    async def handle(self, subject: str, payload: bytes) -> bytes:
        action = self.SUBJECTS.get(subject)
        if action is None:
            return json.dumps({"ok": False, "error": f"未知主题: {subject}"}).encode()
        handler = getattr(self, f"_on_{action}")
        return await handler(payload)

    # 处理新增请求
    async def _on_add(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        result = self._service.add(req.get("ai_id", ""), req)
        return json.dumps(result).encode()

    # 处理检索
    async def _on_search(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        sticker = self._service.search(req.get("ai_id", ""), req.get("query", ""))
        return json.dumps({"sticker": sticker}).encode()

    # 处理列表请求
    async def _on_list(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        stickers = self._service.list(
            req.get("ai_id", ""),
            top_k=int(req.get("top_k", self._service.list_limit)),
        )
        return json.dumps({"stickers": stickers}).encode()

    # 处理记忆增强请求
    async def _on_boost(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        self._service.boost(req.get("ai_id", ""), req.get("sticker_id", ""))
        return json.dumps({"ok": True}).encode()
