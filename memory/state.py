from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass

from shared.contracts.memory import MemoryActivity


@dataclass(frozen=True)
class StateEntry:
    key: str
    revision: int
    data: dict


class MemoryStateStore:
    """用 JetStream KV 保存活动水位和待合并批次。"""

    def __init__(self, activity_kv, pending_kv, quiet_window_sec: float, lease_sec: float) -> None:
        self._activity = activity_kv
        self._pending = pending_kv
        self._quiet_window = float(quiet_window_sec)
        self._lease = float(lease_sec)

    async def record_activity(self, activity: MemoryActivity) -> None:
        key = self._key("activity", activity.ai_id, activity.person_id)
        data = {
            **activity.to_dict(),
            "activity_id": (
                f"{activity.ai_id}:{activity.person_id}:{activity.sequence}:{activity.message_id}"
            ),
            "due_at": activity.active_at + self._quiet_window,
            "status": "active",
            "lease_until": 0.0,
            "claim_id": "",
        }
        for _ in range(8):
            current = await self._get(self._activity, key)
            if current is not None:
                current_order = (
                    int(current.data.get("sequence", 0)),
                    float(current.data.get("active_at", 0)),
                )
                incoming_order = (activity.sequence, activity.active_at)
                if incoming_order <= current_order:
                    return
            if await self._cas(self._activity, key, data, current):
                return
        raise RuntimeError("更新记忆活动状态冲突")

    async def due_activities(self, now: float | None = None) -> list[StateEntry]:
        now = time.time() if now is None else now
        result = []
        for entry in await self._entries(self._activity):
            status = entry.data.get("status", "active")
            lease_until = float(entry.data.get("lease_until", 0))
            if float(entry.data.get("due_at", 0)) <= now and (
                status == "active" or lease_until <= now
            ):
                result.append(entry)
        return result

    async def claim_activity(self, entry: StateEntry, now: float | None = None) -> StateEntry | None:
        now = time.time() if now is None else now
        data = dict(entry.data)
        data.update(
            status="processing",
            lease_until=now + self._lease,
            claim_id=uuid.uuid4().hex,
        )
        revision = await self._update(self._activity, entry.key, data, entry.revision)
        return StateEntry(entry.key, revision, data) if revision else None

    async def finish_activity(self, claim: StateEntry) -> None:
        await self._delete_if_claim(self._activity, claim)

    async def release_activity(self, claim: StateEntry, retry_delay_sec: float) -> None:
        current = await self._get(self._activity, claim.key)
        if current is None or current.data.get("claim_id") != claim.data.get("claim_id"):
            return
        data = dict(current.data)
        data.update(
            status="active",
            due_at=time.time() + retry_delay_sec,
            lease_until=0.0,
            claim_id="",
        )
        await self._update(self._activity, current.key, data, current.revision)

    async def add_pending(
        self,
        ai_id: str,
        owner_type: str,
        owner_id: str,
        episode_id: str,
        atom_ids: list[str],
        estimated_tokens: int,
        added_at: float | None = None,
    ) -> None:
        if not atom_ids:
            return
        added_at = time.time() if added_at is None else added_at
        key = self._key("pending", ai_id, owner_type, owner_id)
        for _ in range(8):
            current = await self._get(self._pending, key)
            data = dict(current.data) if current else {
                "ai_id": ai_id,
                "owner_type": owner_type,
                "owner_id": owner_id,
                "episode_ids": [],
                "atom_ids": [],
                "episode_tokens": {},
                "first_pending_at": added_at,
                "status": "active",
                "lease_until": 0.0,
                "claim_id": "",
            }
            episode_ids = list(data.get("episode_ids", []))
            existing_atoms = list(data.get("atom_ids", []))
            if episode_id not in episode_ids:
                episode_ids.append(episode_id)
                data.setdefault("episode_tokens", {})[episode_id] = int(estimated_tokens)
            data["episode_ids"] = episode_ids
            data["atom_ids"] = list(dict.fromkeys([*existing_atoms, *atom_ids]))
            data["episode_count"] = len(data["episode_ids"])
            data["atom_count"] = len(data["atom_ids"])
            data["estimated_tokens"] = sum(
                int(value) for value in data.get("episode_tokens", {}).values()
            )
            if await self._cas(self._pending, key, data, current):
                return
        raise RuntimeError("更新待合并记忆状态冲突")

    async def ready_pending(self, thresholds: dict[str, dict], now: float | None = None) -> list[StateEntry]:
        now = time.time() if now is None else now
        result = []
        for entry in await self._entries(self._pending):
            data = entry.data
            status = data.get("status", "active")
            if status == "processing" and float(data.get("lease_until", 0)) > now:
                continue
            threshold = thresholds[data.get("owner_type", "person")]
            waited = now - float(data.get("first_pending_at", now))
            if (
                int(data.get("episode_count", 0)) >= int(threshold["min_episode_count"])
                or int(data.get("atom_count", 0)) >= int(threshold["min_atom_count"])
                or int(data.get("estimated_tokens", 0)) >= int(threshold["token_threshold"])
                or waited >= float(threshold["max_wait_sec"])
            ):
                result.append(entry)
        return result

    async def claim_pending(self, entry: StateEntry, now: float | None = None) -> StateEntry | None:
        now = time.time() if now is None else now
        data = dict(entry.data)
        data.update(
            status="processing",
            lease_until=now + self._lease,
            claim_id=uuid.uuid4().hex,
        )
        revision = await self._update(self._pending, entry.key, data, entry.revision)
        return StateEntry(entry.key, revision, data) if revision else None

    async def complete_pending(self, claim: StateEntry) -> None:
        processed_episodes = set(claim.data.get("episode_ids", []))
        processed_atoms = set(claim.data.get("atom_ids", []))
        for _ in range(8):
            current = await self._get(self._pending, claim.key)
            if current is None:
                return
            if current.data.get("claim_id") != claim.data.get("claim_id"):
                return
            remaining_atoms = [
                item for item in current.data.get("atom_ids", []) if item not in processed_atoms
            ]
            if not remaining_atoms:
                if await self._delete(self._pending, current):
                    return
                continue
            remaining_episodes = [
                item for item in current.data.get("episode_ids", []) if item not in processed_episodes
            ]
            episode_tokens = {
                key: value
                for key, value in current.data.get("episode_tokens", {}).items()
                if key in remaining_episodes
            }
            data = dict(current.data)
            data.update(
                episode_ids=remaining_episodes,
                atom_ids=remaining_atoms,
                episode_tokens=episode_tokens,
                episode_count=len(remaining_episodes),
                atom_count=len(remaining_atoms),
                estimated_tokens=sum(int(value) for value in episode_tokens.values()),
                first_pending_at=time.time(),
                status="active",
                lease_until=0.0,
                claim_id="",
            )
            if await self._update(self._pending, current.key, data, current.revision):
                return
        raise RuntimeError("完成待合并记忆状态冲突")

    async def release_pending(self, claim: StateEntry) -> None:
        current = await self._get(self._pending, claim.key)
        if current is None or current.data.get("claim_id") != claim.data.get("claim_id"):
            return
        data = dict(current.data)
        data.update(status="active", lease_until=0.0, claim_id="")
        await self._update(self._pending, current.key, data, current.revision)

    async def _delete_if_claim(self, kv, claim: StateEntry) -> None:
        current = await self._get(kv, claim.key)
        if current is not None and current.data.get("claim_id") == claim.data.get("claim_id"):
            await self._delete(kv, current)

    async def _entries(self, kv) -> list[StateEntry]:
        try:
            keys = await kv.keys()
        except Exception as exc:
            if exc.__class__.__name__ == "NoKeysError":
                return []
            raise
        result = []
        for key in keys:
            entry = await self._get(kv, key)
            if entry is not None:
                result.append(entry)
        return result

    @staticmethod
    async def _get(kv, key: str) -> StateEntry | None:
        try:
            entry = await kv.get(key)
        except Exception as exc:
            if exc.__class__.__name__ in {"KeyNotFoundError", "KeyDeletedError"}:
                return None
            raise
        return StateEntry(
            key=key,
            revision=int(entry.revision),
            data=json.loads(entry.value.decode("utf-8")),
        )

    async def _cas(self, kv, key: str, data: dict, current: StateEntry | None) -> bool:
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            if current is None:
                await kv.create(key, raw)
            else:
                await kv.update(key, raw, current.revision)
            return True
        except Exception as exc:
            if exc.__class__.__name__ == "KeyWrongLastSequenceError":
                return False
            raise

    @staticmethod
    async def _update(kv, key: str, data: dict, revision: int) -> int:
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            return int(await kv.update(key, raw, revision))
        except Exception as exc:
            if exc.__class__.__name__ == "KeyWrongLastSequenceError":
                return 0
            raise

    @staticmethod
    async def _delete(kv, entry: StateEntry) -> bool:
        try:
            await kv.delete(entry.key, last=entry.revision)
            return True
        except Exception as exc:
            if exc.__class__.__name__ == "KeyWrongLastSequenceError":
                return False
            raise

    @staticmethod
    def _key(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
        return f"{prefix}.{digest}"
