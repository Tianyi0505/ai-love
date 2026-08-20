from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from nats.js.errors import KeyDeletedError, KeyNotFoundError, KeyWrongLastSequenceError, NoKeysError
from pydantic import BaseModel, ConfigDict

from shared.configuration.global_settings import MemoryConsolidationSettings
from shared.contracts.memory import MemoryActivity
from shared.infrastructure.snowflake_id_generator import snowflake_ids

StateT = TypeVar("StateT", bound=BaseModel)
StateStatus = Literal["active", "processing"]


class ActivityState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id: str
    person_id: str
    conversation_id: str
    message_id: str
    sequence: int
    active_at: float
    activity_id: str
    due_at: float
    status: StateStatus
    lease_until: float | None
    claim_id: str | None


class PendingState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id: str
    owner_type: Literal["person", "self"]
    owner_id: str
    episode_ids: tuple[str, ...]
    atom_ids: tuple[str, ...]
    episode_tokens: dict[str, int]
    first_pending_at: float
    status: StateStatus
    lease_until: float | None
    claim_id: str | None


@dataclass(frozen=True)
class StateEntry(Generic[StateT]):
    key: str
    revision: int
    data: StateT


class MemoryStateStore:
    def __init__(
        self,
        activity_kv,
        pending_kv,
        quiet_window_sec: float,
        lease_sec: float,
        cas_retry_count: int,
    ) -> None:
        self._activity = activity_kv
        self._pending = pending_kv
        self._quiet_window = quiet_window_sec
        self._lease = lease_sec
        self._cas_retry_count = cas_retry_count

    async def record_activity(self, activity: MemoryActivity) -> None:
        key = self._key("activity", activity.ai_id, activity.person_id)
        state = ActivityState(
            **activity.model_dump(),
            activity_id=f"{activity.ai_id}:{activity.person_id}:{activity.sequence}:{activity.message_id}",
            due_at=activity.active_at + self._quiet_window,
            status="active",
            lease_until=None,
            claim_id=None,
        )
        for _ in range(self._cas_retry_count):
            current = await self._get(self._activity, key, ActivityState)
            if current is not None and (activity.sequence, activity.active_at) <= (
                current.data.sequence,
                current.data.active_at,
            ):
                return
            if await self._cas(self._activity, key, state, current):
                return
        raise RuntimeError("更新记忆活动状态冲突")

    async def due_activities(self, now: float | None = None) -> list[StateEntry[ActivityState]]:
        moment = time.time() if now is None else now
        return [
            entry
            for entry in await self._entries(self._activity, ActivityState)
            if entry.data.due_at <= moment
            and (
                entry.data.status == "active"
                or (entry.data.lease_until is not None and entry.data.lease_until <= moment)
            )
        ]

    async def claim_activity(
        self,
        entry: StateEntry[ActivityState],
        now: float | None = None,
    ) -> StateEntry[ActivityState] | None:
        moment = time.time() if now is None else now
        state = entry.data.model_copy(
            update={
                "status": "processing",
                "lease_until": moment + self._lease,
                "claim_id": str(snowflake_ids().next_id()),
            }
        )
        revision = await self._update(self._activity, entry.key, state, entry.revision)
        return StateEntry(entry.key, revision, state) if revision is not None else None

    async def finish_activity(self, claim: StateEntry[ActivityState]) -> None:
        await self._delete_if_claim(self._activity, claim, ActivityState)

    async def release_activity(self, claim: StateEntry[ActivityState], retry_delay_sec: float) -> None:
        current = await self._get(self._activity, claim.key, ActivityState)
        if current is None or current.data.claim_id != claim.data.claim_id:
            return
        state = current.data.model_copy(
            update={
                "status": "active",
                "due_at": time.time() + retry_delay_sec,
                "lease_until": None,
                "claim_id": None,
            }
        )
        await self._update(self._activity, current.key, state, current.revision)

    async def add_pending(
        self,
        ai_id: str,
        owner_type: Literal["person", "self"],
        owner_id: str,
        episode_id: str,
        atom_ids: list[str],
        estimated_tokens: int,
        added_at: float | None = None,
    ) -> None:
        if not atom_ids:
            return
        moment = time.time() if added_at is None else added_at
        key = self._key("pending", ai_id, owner_type, owner_id)
        for _ in range(self._cas_retry_count):
            current = await self._get(self._pending, key, PendingState)
            if current is None:
                state = PendingState(
                    ai_id=ai_id,
                    owner_type=owner_type,
                    owner_id=owner_id,
                    episode_ids=(episode_id,),
                    atom_ids=tuple(dict.fromkeys(atom_ids)),
                    episode_tokens={episode_id: estimated_tokens},
                    first_pending_at=moment,
                    status="active",
                    lease_until=None,
                    claim_id=None,
                )
            else:
                episodes = list(current.data.episode_ids)
                tokens = dict(current.data.episode_tokens)
                if episode_id not in episodes:
                    episodes.append(episode_id)
                    tokens[episode_id] = estimated_tokens
                state = current.data.model_copy(
                    update={
                        "episode_ids": tuple(episodes),
                        "atom_ids": tuple(dict.fromkeys((*current.data.atom_ids, *atom_ids))),
                        "episode_tokens": tokens,
                    }
                )
            if await self._cas(self._pending, key, state, current):
                return
        raise RuntimeError("更新待合并记忆状态冲突")

    async def ready_pending(
        self,
        thresholds: MemoryConsolidationSettings,
        now: float | None = None,
    ) -> list[StateEntry[PendingState]]:
        moment = time.time() if now is None else now
        result: list[StateEntry[PendingState]] = []
        for entry in await self._entries(self._pending, PendingState):
            state = entry.data
            if state.status == "processing" and state.lease_until is not None and state.lease_until > moment:
                continue
            threshold = getattr(thresholds, state.owner_type)
            if (
                len(state.episode_ids) >= threshold.min_episode_count
                or len(state.atom_ids) >= threshold.min_atom_count
                or sum(state.episode_tokens.values()) >= threshold.token_threshold
                or moment - state.first_pending_at >= threshold.max_wait_sec
            ):
                result.append(entry)
        return result

    async def claim_pending(
        self,
        entry: StateEntry[PendingState],
        now: float | None = None,
    ) -> StateEntry[PendingState] | None:
        moment = time.time() if now is None else now
        state = entry.data.model_copy(
            update={
                "status": "processing",
                "lease_until": moment + self._lease,
                "claim_id": str(snowflake_ids().next_id()),
            }
        )
        revision = await self._update(self._pending, entry.key, state, entry.revision)
        return StateEntry(entry.key, revision, state) if revision is not None else None

    async def complete_pending(self, claim: StateEntry[PendingState]) -> None:
        processed_episodes = set(claim.data.episode_ids)
        processed_atoms = set(claim.data.atom_ids)
        for _ in range(self._cas_retry_count):
            current = await self._get(self._pending, claim.key, PendingState)
            if current is None or current.data.claim_id != claim.data.claim_id:
                return
            remaining_atoms = tuple(item for item in current.data.atom_ids if item not in processed_atoms)
            if not remaining_atoms:
                if await self._delete(self._pending, current):
                    return
                continue
            remaining_episodes = tuple(item for item in current.data.episode_ids if item not in processed_episodes)
            episode_tokens = {
                key: value for key, value in current.data.episode_tokens.items() if key in remaining_episodes
            }
            state = current.data.model_copy(
                update={
                    "episode_ids": remaining_episodes,
                    "atom_ids": remaining_atoms,
                    "episode_tokens": episode_tokens,
                    "first_pending_at": time.time(),
                    "status": "active",
                    "lease_until": None,
                    "claim_id": None,
                }
            )
            if await self._update(self._pending, current.key, state, current.revision) is not None:
                return
        raise RuntimeError("完成待合并记忆状态冲突")

    async def release_pending(self, claim: StateEntry[PendingState]) -> None:
        current = await self._get(self._pending, claim.key, PendingState)
        if current is None or current.data.claim_id != claim.data.claim_id:
            return
        state = current.data.model_copy(update={"status": "active", "lease_until": None, "claim_id": None})
        await self._update(self._pending, current.key, state, current.revision)

    async def _delete_if_claim(
        self,
        kv,
        claim: StateEntry[StateT],
        state_type: type[StateT],
    ) -> None:
        current = await self._get(kv, claim.key, state_type)
        if current is not None and current.data.claim_id == claim.data.claim_id:
            await self._delete(kv, current)

    async def _entries(self, kv, state_type: type[StateT]) -> list[StateEntry[StateT]]:
        try:
            keys = await kv.keys()
        except NoKeysError:
            return []
        entries = [await self._get(kv, key, state_type) for key in keys]
        return [entry for entry in entries if entry is not None]

    @staticmethod
    async def _get(kv, key: str, state_type: type[StateT]) -> StateEntry[StateT] | None:
        try:
            entry = await kv.get(key)
        except (KeyNotFoundError, KeyDeletedError):
            return None
        return StateEntry(
            key=key,
            revision=int(entry.revision),
            data=state_type.model_validate_json(entry.value),
        )

    async def _cas(
        self,
        kv,
        key: str,
        state: StateT,
        current: StateEntry[StateT] | None,
    ) -> bool:
        raw = state.model_dump_json().encode()
        try:
            if current is None:
                await kv.create(key, raw)
            else:
                await kv.update(key, raw, current.revision)
            return True
        except KeyWrongLastSequenceError:
            return False

    @staticmethod
    async def _update(kv, key: str, state: StateT, revision: int) -> int | None:
        try:
            return int(await kv.update(key, state.model_dump_json().encode(), revision))
        except KeyWrongLastSequenceError:
            return None

    @staticmethod
    async def _delete(kv, entry: StateEntry[StateT]) -> bool:
        try:
            await kv.delete(entry.key, last=entry.revision)
            return True
        except KeyWrongLastSequenceError:
            return False

    @staticmethod
    def _key(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
        return f"{prefix}.{digest}"
