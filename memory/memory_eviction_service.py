from __future__ import annotations

import time

from sqlalchemy import delete, select

from memory.memory_policy import MemoryType
from shared.persistence import database_models as m
from shared.utils.lfu import LazyLFU


class MemoryEvictionService:
    def __init__(
        self,
        db,
        lfu: LazyLFU,
        *,
        record_capacity_per_owner: int,
        atom_capacity_per_owner: int,
        deletable_reference_count: int,
    ) -> None:
        self._db = db
        self._lfu = lfu
        self._record_capacity = record_capacity_per_owner
        self._atom_capacity = atom_capacity_per_owner
        self._deletable_reference_count = deletable_reference_count

    def _score(self, value: dict | None, now: float) -> float:
        return self._lfu.score(self._lfu.state_from_mapping(value, now), now)

    async def evict_memories(self, owner_ai_id: str) -> int:
        async with self._db.session() as session:
            async with session.begin():
                rows = list(
                    (
                        await session.execute(
                            select(m.Memory)
                            .where(m.Memory.owner_ai_id == owner_ai_id)
                            .with_for_update()
                        )
                    ).scalars()
                )
                excess = max(0, len(rows) - self._record_capacity)
                if excess == 0:
                    return 0
                now = time.time()
                candidates = [
                    row
                    for row in rows
                    if row.consolidated
                    and not row.protected
                    and row.memory_type != MemoryType.COMMITMENT.value
                    and row.reference_count == self._deletable_reference_count
                ]
                candidates.sort(
                    key=lambda row: (
                        self._score(row.lfu_state, now),
                        float(row.importance),
                        float(row.confidence),
                        row.created_at,
                        row.memory_id,
                    )
                )
                evicted_ids = [row.memory_id for row in candidates[:excess]]
                if evicted_ids:
                    await session.execute(delete(m.Memory).where(m.Memory.memory_id.in_(evicted_ids)))
                return len(evicted_ids)

    async def evict_atoms_for_ids(self, atom_ids: list[str]) -> int:
        if not atom_ids:
            return 0
        async with self._db.session() as session:
            async with session.begin():
                owner_rows = await session.execute(
                    select(m.MemoryAtom.ai_id, m.MemoryAtom.owner_type, m.MemoryAtom.owner_id)
                    .where(m.MemoryAtom.atom_id.in_([int(item) for item in atom_ids]))
                    .distinct()
                )
                owners = {(row.ai_id, row.owner_type, row.owner_id) for row in owner_rows}
                evicted = 0
                for ai_id, owner_type, owner_id in owners:
                    rows = list(
                        (
                            await session.execute(
                                select(m.MemoryAtom)
                                .where(
                                    m.MemoryAtom.ai_id == ai_id,
                                    m.MemoryAtom.owner_type == owner_type,
                                    m.MemoryAtom.owner_id == owner_id,
                                )
                                .with_for_update()
                            )
                        ).scalars()
                    )
                    excess = max(0, len(rows) - self._atom_capacity)
                    if excess == 0:
                        continue
                    now = time.time()
                    candidates = [row for row in rows if row.consolidated_at is not None]
                    candidates.sort(
                        key=lambda row: (
                            self._score(row.lfu_state, now),
                            float(row.importance),
                            float(row.confidence),
                            row.created_at,
                            row.atom_id,
                        )
                    )
                    evicted_ids = [row.atom_id for row in candidates[:excess]]
                    if evicted_ids:
                        await session.execute(delete(m.MemoryAtom).where(m.MemoryAtom.atom_id.in_(evicted_ids)))
                    evicted += len(evicted_ids)
                return evicted
