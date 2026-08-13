
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from shared.contracts.relationship import RelationshipCeilings, RelationshipPolicy
from shared.infrastructure.agent_store import NacosAgentDefinitionStore
from shared.infrastructure.config import ServiceConfig
from shared.infrastructure.database import Database
from shared.infrastructure.global_config import GlobalConfig
from shared.infrastructure.repositories import RelationshipRepository
from shared.infrastructure.service import BaseService

from memory.controllers.sticker_controller import StickerController
from memory.memory_policy import MemoryPolicy
from memory.repositories.memory_repo import MemoryRepo
from memory.repositories.postgres_memory_repo import PostgresMemoryRepo
from memory.services.sticker_service import StickerService

logger = logging.getLogger("ailove.memory")

class MemoryService(BaseService):
    name = "memory"

    async def on_start(self) -> None:
        self._gcfg = GlobalConfig(provider=self.cfg.nacos)
        await self._gcfg.load()
        self._memory_config = self._gcfg.section("memory")

        self._sticker_svc = StickerService(self._gcfg)
        self._db = None
        self._relationship_repo = None
        self._definitions = NacosAgentDefinitionStore(self.cfg.nacos)
        if os.environ.get("AILOVE_DATABASE_URL"):
            self._db = Database()
            await self._db.connect()
            self._memory_repo = PostgresMemoryRepo(
                self._db,
                MemoryPolicy(
                    half_life_sec=float(self._memory_config["half_life_sec"]),
                    dormant_threshold=float(self._memory_config["dormant_threshold"]),
                    delete_threshold=float(self._memory_config["delete_threshold"]),
                    recall_boost=float(self._memory_config["recall_boost"]),
                    retrieval_weights=dict(self._memory_config["retrieval_weights"]),
                ),
                self._memory_config,
            )
            self._relationship_repo = RelationshipRepository(self._db)
        else:
            self._memory_repo = MemoryRepo(str(self._memory_config["data_dir"]))

        self._sticker_ctrl = StickerController(self._sticker_svc)
        self._controllers = {"sticker": self._sticker_ctrl}

        for subject, action in StickerController.SUBJECTS.items():
            await self.bus.reply(subject, self._make_sticker_handler(action))

        await self.bus.reply("memory.write.request", self._on_write)
        await self.bus.reply("memory.search.request", self._on_search)
        await self.bus.reply("memory.procedural.request", self._on_procedural)
        await self.bus.reply("memory.batch.request", self._on_batch)
        await self.bus.reply("relationship.gift.request", self._on_relationship_gift)
        await self.bus.reply("relationship.chat.request", self._on_relationship_chat)
        await self.bus.reply("relationship.summary.request", self._on_relationship_summary)
        await self.bus.reply("relationship.list.request", self._on_relationship_list)
        await self.bus.reply("relationship.group.request", self._on_group_relationship)

        self.spawn(self._cleanup_loop())

    async def on_stop(self) -> None:
        self._sticker_svc.close()
        if self._db is not None:
            await self._db.close()

    def _make_sticker_handler(self, action: str):

        async def handler(payload: bytes) -> bytes:
            method = getattr(self._sticker_ctrl, f"_on_{action}")
            return await method(payload)

        return handler

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(float(self._memory_config["cleanup_interval_sec"]))
            removed = self._sticker_svc.cleanup()
            memory_result = await self._memory_repo.cleanup()
            files = self._cleanup_old_files(
                str(self._memory_config["data_dir"]),
                float(self._memory_config["file_max_age_sec"]),
            )
            logger.info(
                "[memory] 每日清理（表情 %s 个，记忆休眠 %s 个，记忆删除 %s 个，过期文件 %s 个）",
                removed,
                memory_result.get("dormant", 0),
                memory_result.get("deleted", 0),
                files,
            )

    def _cleanup_old_files(self, data_dir: str, max_age_sec: float) -> int:
        cutoff = time.time() - max_age_sec
        removed = 0
        for root, _, files in os.walk(data_dir):
            for f in files:
                path = os.path.join(root, f)
                if f.endswith(".db"):
                    continue
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        removed += 1
                except OSError:
                    pass
        return removed

    async def _on_write(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        ai_id = req.get("ai_id", "")
        entries = req.get("entries", [])
        for e in entries:
            e.setdefault("scope", self._memory_config["default_scope"])
            e.setdefault("memory_type", e.get("kind", self._memory_config["default_type"]))
            e.setdefault("importance", self._memory_config["default_importance"])
            e.setdefault("strength", self._memory_config["default_strength"])
            e.setdefault("confidence", self._memory_config["default_confidence"])
            e.setdefault("emotion_intensity", self._memory_config["default_emotion_intensity"])
            e.setdefault("consolidated", self._memory_config["default_consolidated"])
        await self._memory_repo.write(ai_id, entries)
        logger.info("[memory] 写入 %s 条: ai=%s", len(entries), ai_id)
        return json.dumps({"ok": True}).encode()

    async def _on_search(self, payload: bytes) -> bytes:
        req = json.loads(payload.decode("utf-8"))
        results = await self._memory_repo.search(
            req.get("ai_id", ""),
            req.get("query", ""),
            int(req.get("top_k", self._memory_config["search_top_k"])),
            person_id=req.get("person_id", ""),
            session_id=req.get("session_id", ""),
            active_session_actors=req.get("active_session_actors", []),
        )
        return json.dumps({"results": results}).encode()

    async def _on_procedural(self, payload: bytes) -> bytes:
        return json.dumps({"rules": []}).encode()

    async def _on_batch(self, payload: bytes) -> bytes:
        return json.dumps({"semantic": [], "rules": [], "viewer_profile": None}).encode()

    async def _relationship_policy(self, ai_id: str) -> RelationshipPolicy:
        raw = (await self._definitions.load(ai_id)).relationship_policy
        person_whitelist = {str(item) for item in raw["person_ceiling_whitelist"]}
        if raw["inherit_qq_whitelist_ceiling"]:
            qq_whitelist = self._gcfg.get("qq", "whitelist")
            if isinstance(qq_whitelist, dict):
                qq_whitelist = qq_whitelist["user_ids"]
            person_whitelist.update(str(item) for item in qq_whitelist)
        ceilings = RelationshipCeilings(
            default=float(raw["default_ceiling"]),
            whitelist=float(raw["whitelist_ceiling"]),
            person_whitelist=frozenset(person_whitelist),
            group_whitelist=frozenset(str(item) for item in raw["group_ceiling_whitelist"]),
        )
        return RelationshipPolicy(ceilings, raw)

    def _is_priority_user(self, platform_user_id: str) -> bool:
        whitelist = self._gcfg.get("qq", "whitelist")
        if isinstance(whitelist, dict):
            whitelist = whitelist["user_ids"]
        return str(platform_user_id) in {str(item) for item in whitelist}

    async def _on_relationship_chat(self, payload: bytes) -> bytes:
        req = json.loads(payload)
        if self._relationship_repo is None or not req.get("ai_id") or not req.get("person_id"):
            return json.dumps({"ok": False, "reason": "关系存储未启用或缺少身份"}).encode()
        ai_id = str(req["ai_id"])
        person_id = str(req["person_id"])
        policy = await self._relationship_policy(ai_id)
        current = await self._relationship_repo.get_person(ai_id, person_id)
        ceiling_identity = str(req.get("platform_user_id") or person_id)
        updated = policy.on_conversation(ceiling_identity, current, float(req.get("quality", 0.0)))
        ceiling_policy = "whitelist" if self._is_priority_user(ceiling_identity) else "default"
        await self._relationship_repo.save_person(ai_id, person_id, updated, ceiling_policy)
        if req.get("chat_type") == "group" and req.get("group_id") and req.get("account_id"):
            group_id = str(req["group_id"])
            group = await self._relationship_repo.get_group(ai_id, str(req["account_id"]), group_id)
            group = policy.on_group_conversation(group_id, group, float(req.get("quality", 0.0)))
            await self._relationship_repo.save_group(ai_id, str(req["account_id"]), group_id, group)
        return json.dumps({"ok": True, "summary": policy.summarize_person(updated)}, ensure_ascii=False).encode()

    async def _on_relationship_gift(self, payload: bytes) -> bytes:
        req = json.loads(payload)
        if self._relationship_repo is None or not req.get("ai_id") or not req.get("person_id"):
            return json.dumps({"ok": False, "reason": "关系存储未启用或缺少身份"}).encode()
        ai_id = str(req["ai_id"])
        person_id = str(req["person_id"])
        policy = await self._relationship_policy(ai_id)
        current = await self._relationship_repo.get_person(ai_id, person_id)
        ceiling_identity = str(req.get("platform_user_id") or person_id)
        updated = policy.on_gift(ceiling_identity, current, float(req.get("amount", 0.0)))
        ceiling_policy = "whitelist" if self._is_priority_user(ceiling_identity) else "default"
        await self._relationship_repo.save_person(ai_id, person_id, updated, ceiling_policy)
        return json.dumps({"ok": True, "summary": policy.summarize_person(updated)}, ensure_ascii=False).encode()

    async def _on_relationship_summary(self, payload: bytes) -> bytes:
        req = json.loads(payload)
        if self._relationship_repo is None or not req.get("ai_id") or not req.get("person_id"):
            return json.dumps(
                {"summary": self._gcfg.get("fallbacks", "relationship_unknown")},
                ensure_ascii=False,
            ).encode()
        ai_id = str(req["ai_id"])
        relationship = await self._relationship_repo.get_person(ai_id, str(req["person_id"]))
        summary = (await self._relationship_policy(ai_id)).summarize_person(relationship)
        return json.dumps({"summary": summary}, ensure_ascii=False).encode()

    async def _on_relationship_list(self, payload: bytes) -> bytes:
        req = json.loads(payload)
        if self._relationship_repo is None:
            return json.dumps({"relationships": []}).encode()
        relationships = await self._relationship_repo.list_people(str(req.get("ai_id", "")))
        whitelist = self._gcfg.get("qq", "whitelist")
        if isinstance(whitelist, dict):
            whitelist = whitelist["user_ids"]
        priority_user_ids = {str(item) for item in whitelist}
        for relationship in relationships:
            relationship["priority_contact"] = str(relationship.get("user_id", "")) in priority_user_ids
        return json.dumps({"relationships": relationships}, ensure_ascii=False, default=str).encode()

    async def _on_group_relationship(self, payload: bytes) -> bytes:
        req = json.loads(payload)
        if self._relationship_repo is None:
            return json.dumps({"relationship": {}}).encode()
        ai_id = str(req.get("ai_id", ""))
        account_id = str(req.get("account_id", ""))
        group_id = str(req.get("group_id", ""))
        if not ai_id or not account_id or not group_id:
            return json.dumps({"relationship": {}}).encode()
        relationship = await self._relationship_repo.get_group(ai_id, account_id, group_id)
        return json.dumps(
            {
                "relationship": {
                    "familiarity": relationship.familiarity,
                    "belonging": relationship.belonging,
                    "affinity": relationship.affinity,
                    "activity_willingness": relationship.activity_willingness,
                }
            },
            ensure_ascii=False,
        ).encode()


def main() -> None:
    async def run() -> None:
        svc = MemoryService(await ServiceConfig.load("memory"))
        await svc.start()
        await svc.serve_forever()

    asyncio.run(run())


if __name__ == "__main__":
    main()
