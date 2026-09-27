from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml

from memory.episode_memory_repository import EpisodeMemoryRepository
from memory.memory_eviction_service import MemoryEvictionService
from memory.memory_policy import MemoryPolicy, MemoryRecord, MemoryScope, MemoryType
from memory.relationship_handler import RelationshipHandler
from shared.contracts.relationship import (
    GroupRelationship,
    PersonRelationship,
    RelationshipCeilings,
    RelationshipPolicy,
)
from shared.contracts.relationship_policy_config import RelationshipPolicyConfig
from shared.contracts.rpc.relationship import GroupRelationshipRequest, RelationshipChatRequest
from shared.contracts.tools import ToolExecutionContext
from shared.global_settings import GlobalSettings
from shared.lfu import LazyLFU, LFUConfig, LFUState
from shared.person_resolver import PersonResolver

ROOT = Path(__file__).resolve().parents[1]


def _settings(qq_whitelist: list[int] | None = None) -> GlobalSettings:
    raw = yaml.safe_load((ROOT / "deploy" / "config" / "ailove.config.yaml").read_text(encoding="utf-8"))
    raw["qq"]["whitelist"] = qq_whitelist or []
    return GlobalSettings.model_validate(raw)


def _relationship_config() -> RelationshipPolicyConfig:
    raw = yaml.safe_load((ROOT / "deploy" / "config" / "agent.default.yaml").read_text(encoding="utf-8"))
    return RelationshipPolicyConfig.model_validate(raw["relationship_policy"])


class LazyLFUTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lfu = LazyLFU(
            LFUConfig(
                decay_interval_sec=10,
                log_factor=10,
                log_offset=5,
                max_counter=255,
                score_counter_ceiling=20,
                initial_counter=0,
            ),
            random_value=lambda: 0.0,
        )

    def test_age_consumes_complete_periods_and_preserves_remainder(self) -> None:
        state = LFUState(counter=8, last_decay_at=100.0)

        aged = self.lfu.age(state, 135.0)

        self.assertEqual(LFUState(counter=5, last_decay_at=130.0), aged)
        self.assertEqual(LFUState(counter=4, last_decay_at=140.0), self.lfu.age(aged, 145.0))

    def test_score_is_read_only_and_access_first_applies_decay(self) -> None:
        state = LFUState(counter=8, last_decay_at=100.0)

        self.assertEqual(0.25, self.lfu.score(state, 135.0))
        self.assertEqual(LFUState(counter=8, last_decay_at=100.0), state)
        self.assertEqual(LFUState(counter=6, last_decay_at=130.0), self.lfu.access(state, 135.0))

    def test_probability_source_controls_logarithmic_growth(self) -> None:
        growing = self.lfu.access(self.lfu.initial(100.0), 100.0, hits=3)
        stable_lfu = LazyLFU(self.lfu.config, random_value=lambda: 1.0)

        self.assertEqual(3, growing.counter)
        self.assertEqual(0, stable_lfu.access(stable_lfu.initial(100.0), 100.0).counter)


class RelationshipLFUTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000.0
        self.lfu = LazyLFU(
            LFUConfig(**_settings().lfu.relationship.model_dump()),
            random_value=lambda: 0.0,
        )
        self.policy = RelationshipPolicy(
            RelationshipCeilings(0.7, 1.0, frozenset(), frozenset()),
            _relationship_config(),
            self.lfu,
            now_value=lambda: self.now,
        )

    def test_neutral_chat_only_accesses_familiarity(self) -> None:
        updated = self.policy.on_conversation("person", PersonRelationship(0, 0, 0, 0), 0.0)

        self.assertEqual(0.05, updated.familiarity)
        self.assertEqual(0.0, updated.affinity)
        self.assertEqual(0.0, updated.trust)
        self.assertEqual(1, updated.lfu_state["familiarity"]["counter"])
        self.assertEqual(0, updated.lfu_state["affinity_positive"]["counter"])

    def test_positive_and_negative_signals_use_independent_counters(self) -> None:
        positive = self.policy.on_conversation("person", PersonRelationship(0, 0, 0, 0), 1.0)
        balanced = self.policy.on_conversation("person", positive, -1.0)

        self.assertEqual(0.05, positive.affinity)
        self.assertEqual(0.0, balanced.affinity)
        self.assertEqual(1, balanced.lfu_state["affinity_positive"]["counter"])
        self.assertEqual(1, balanced.lfu_state["affinity_negative"]["counter"])

    def test_stored_whitelist_policy_preserves_full_projection_ceiling(self) -> None:
        state = self.lfu.initial(self.now, counter=20).as_dict()
        current = PersonRelationship(
            0,
            0,
            0,
            0,
            {"familiarity": state},
            "whitelist",
        )

        projected = self.policy.project_person("internal-person-id", current)

        self.assertEqual(1.0, projected.familiarity)
        self.assertEqual(1.0, projected.affinity)

    def test_whitelisted_person_affinity_stays_at_ceiling(self) -> None:
        policy = RelationshipPolicy(
            RelationshipCeilings(0.7, 1.0, frozenset({"priority-person"}), frozenset()),
            _relationship_config(),
            self.lfu,
            now_value=lambda: self.now,
        )

        updated = policy.on_conversation(
            "priority-person",
            PersonRelationship(0, -0.5, 0, 0),
            -1.0,
        )
        self.now += self.lfu.config.decay_interval_sec * 100
        projected = policy.project_person("priority-person", updated)

        self.assertEqual(1.0, updated.affinity)
        self.assertEqual(1.0, projected.affinity)
        self.assertEqual(10, updated.lfu_state["affinity_negative"]["counter"])

    def test_whitelisted_group_affinity_stays_at_ceiling(self) -> None:
        policy = RelationshipPolicy(
            RelationshipCeilings(0.7, 1.0, frozenset(), frozenset({"priority-group"})),
            _relationship_config(),
            self.lfu,
            now_value=lambda: self.now,
        )

        updated = policy.on_group_conversation(
            "priority-group",
            GroupRelationship(0, 0, -0.5, 0),
            -1.0,
        )
        self.now += self.lfu.config.decay_interval_sec * 100
        projected = policy.project_group("priority-group", updated)

        self.assertEqual(1.0, updated.affinity)
        self.assertEqual(1.0, projected.affinity)
        self.assertEqual(10, updated.lfu_state["affinity_negative"]["counter"])


class _RelationshipRepository:
    def __init__(self) -> None:
        self.person = None
        self.group = None

    async def get_group(self, ai_id: str, account_id: str, group_id: str) -> GroupRelationship:
        return GroupRelationship(0, 0, 0, 0)

    async def update_person(self, ai_id, person_id, ceiling_policy, updater):
        self.person = updater(PersonRelationship(0, 0, 0, 0, {}, ceiling_policy))
        return self.person

    async def update_group(self, ai_id, account_id, group_id, updater):
        self.group = updater(GroupRelationship(0, 0, 0, 0))
        return self.group


class _RelationshipDefinitions:
    async def load(self, ai_id: str):
        return SimpleNamespace(relationship_policy=_relationship_config())


class RelationshipHandlerLFUTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_rpc_returns_only_public_projection_fields(self) -> None:
        handler = RelationshipHandler(
            _RelationshipRepository(),
            _RelationshipDefinitions(),
            _settings(),
        )

        response = await handler.group(GroupRelationshipRequest(ai_id="ai", account_id="account", group_id="group"))

        self.assertEqual(
            {"familiarity", "belonging", "affinity", "activity_willingness"},
            set(response.relationship.model_dump()),
        )

    async def test_chat_rpc_routes_real_person_and_group_events_to_lfu(self) -> None:
        repository = _RelationshipRepository()
        handler = RelationshipHandler(repository, _RelationshipDefinitions(), _settings())

        await handler.chat(
            RelationshipChatRequest(
                ai_id="ai",
                person_id="123",
                platform_user_id="456",
                account_id="account",
                chat_type="group",
                group_id="group",
                quality=0,
            )
        )

        self.assertEqual(1, repository.person.lfu_state["familiarity"]["counter"])
        self.assertEqual(1, repository.group.lfu_state["familiarity"]["counter"])
        self.assertEqual(0, repository.person.lfu_state["affinity_positive"]["counter"])

    async def test_chat_rpc_keeps_whitelisted_person_and_group_affinity_at_ceiling(self) -> None:
        repository = _RelationshipRepository()
        handler = RelationshipHandler(
            repository,
            _RelationshipDefinitions(),
            _settings([456]),
        )

        await handler.chat(
            RelationshipChatRequest(
                ai_id="ai",
                person_id="123",
                platform_user_id="456",
                account_id="account",
                chat_type="group",
                group_id="782795932",
                quality=-1,
            )
        )

        self.assertEqual(1.0, repository.person.affinity)
        self.assertEqual(1.0, repository.group.affinity)
        self.assertEqual(0, repository.person.lfu_state["affinity_negative"]["counter"])
        self.assertEqual(0, repository.group.lfu_state["affinity_negative"]["counter"])


class MemoryLFUTests(unittest.TestCase):
    def test_protected_memory_uses_the_same_lfu_strength_projection(self) -> None:
        lfu = LazyLFU(
            LFUConfig(10, 10, 5, 255, 20, 10),
            random_value=lambda: 0.0,
        )
        policy = MemoryPolicy(
            dormant_threshold=0.2,
            delete_threshold=0.05,
            strength_max=1.0,
            deletable_reference_count=0,
            recall_count_increment=1,
            retrieval_weights={
                "relevance": 1,
                "strength": 0,
                "importance": 0,
                "confidence": 0,
                "emotion_intensity": 0,
            },
            lfu=lfu,
        )
        memory = MemoryRecord(
            memory_id="1",
            owner_ai_id="ai",
            scope=MemoryScope.PRIVATE,
            memory_type=MemoryType.COMMITMENT,
            content="约定",
            importance=1,
            strength=1,
            confidence=1,
            emotion_intensity=0,
            session_id=None,
            shared_with=frozenset(),
            protected=True,
            consolidated=True,
            reference_count=0,
            last_strength_at=100,
            last_recalled_at=None,
            recall_count=0,
            lfu_state=LFUState(10, 100).as_dict(),
        )

        self.assertEqual(0.25, policy.current_strength(memory, 150))
        self.assertFalse(policy.can_delete(memory, 1_000))


class _Result:
    def __init__(self, value=None) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _EvidenceDB:
    def __init__(self) -> None:
        self.inserted = False
        self.frequency_updates = 0

    def session(self):
        return _EvidenceSession(self)


class _EvidenceSession:
    def __init__(self, db: _EvidenceDB) -> None:
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        sql = str(statement).lower()
        if sql.startswith("insert into person_mentions"):
            if self._db.inserted:
                return _Result()
            self._db.inserted = True
            return _Result(1)
        if sql.startswith("select person_mention_frequencies"):
            return _Result(
                SimpleNamespace(
                    person_mention_frequency_id=2,
                    lfu_state=LFUState(0, 1_000).as_dict(),
                )
            )
        if sql.startswith("update person_mention_frequencies"):
            self._db.frequency_updates += 1
        return _Result()

    async def commit(self) -> None:
        pass


class EvidenceLFUTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_message_retry_accesses_frequency_once(self) -> None:
        db = _EvidenceDB()
        settings = _settings()
        resolver = PersonResolver(
            db,
            settings.grounding,
            LazyLFU(LFUConfig(**settings.lfu.evidence.model_dump()), random_value=lambda: 0.0),
        )
        evidence = {
            "mention_text": "老王",
            "person_id": "123",
            "scope_type": "group",
            "scope_id": "456",
            "conversation_id": "789",
            "source_message_id": "message-1",
            "evidence_type": "explicit_at",
            "confidence": 1.0,
        }

        await resolver.record_evidence(**evidence)
        await resolver.record_evidence(**evidence)

        self.assertEqual(1, db.frequency_updates)

    async def test_resolve_ranks_candidates_by_lazy_frequency_projection(self) -> None:
        settings = _settings()
        now = datetime.now(timezone.utc)
        db = _ResolveEvidenceDB(now)
        resolver = PersonResolver(
            db,
            settings.grounding,
            LazyLFU(LFUConfig(**settings.lfu.evidence.model_dump())),
        )

        result = await resolver.resolve(
            ToolExecutionContext(
                platform="qq",
                account_id="account",
                chat_type="group",
                chat_id="group",
                conversation_id="789",
            ),
            "老王",
            2,
        )

        self.assertEqual(["2", "1"], [candidate.person_id for candidate in result.candidates])
        self.assertGreater(result.candidates[0].confidence, result.candidates[1].confidence)


class _ResolveEvidenceDB:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def session(self):
        return _ResolveEvidenceSession(self)


class _ResolveEvidenceSession:
    def __init__(self, db: _ResolveEvidenceDB) -> None:
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        sql = str(statement).lower()
        if "from person_mention_frequencies" in sql:
            return [
                SimpleNamespace(
                    person_id=1,
                    scope_type="group",
                    scope_id="group",
                    lfu_state=LFUState(1, self._db.now.timestamp()).as_dict(),
                ),
                SimpleNamespace(
                    person_id=2,
                    scope_type="group",
                    scope_id="group",
                    lfu_state=LFUState(8, self._db.now.timestamp()).as_dict(),
                ),
            ]
        if "from person_mentions" in sql:
            return [
                SimpleNamespace(
                    person_id=1,
                    display_name="偶然称呼",
                    scope_type="group",
                    scope_id="group",
                    confidence=1.0,
                    evidence_count=20,
                    last_seen_at=self._db.now,
                    age_sec=0,
                ),
                SimpleNamespace(
                    person_id=2,
                    display_name="稳定称呼",
                    scope_type="group",
                    scope_id="group",
                    confidence=0.8,
                    evidence_count=8,
                    last_seen_at=self._db.now,
                    age_sec=0,
                ),
            ]
        return []


class _EvictionResult(list):
    def scalars(self):
        return self


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _EvictionDB:
    def __init__(self, atoms) -> None:
        self.atoms = atoms
        self.deleted_ids = []

    def session(self):
        return _EvictionSession(self)


class _EvictionSession:
    def __init__(self, db: _EvictionDB) -> None:
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return _Transaction()

    async def execute(self, statement):
        if getattr(statement, "is_delete", False):
            params = statement.compile().params
            self._db.deleted_ids.extend(next(value for value in params.values() if isinstance(value, list)))
            return _EvictionResult()
        sql = str(statement).lower()
        if "select distinct memory_atoms.ai_id" in sql:
            return _EvictionResult([SimpleNamespace(ai_id="ai", owner_type="person", owner_id="person")])
        if "from memory_atoms" in sql:
            return _EvictionResult(self._db.atoms)
        return _EvictionResult()


class MemoryEvictionTests(unittest.IsolatedAsyncioTestCase):
    async def test_atom_eviction_removes_exact_excess_in_lfu_order(self) -> None:
        now = datetime.now(timezone.utc)
        atoms = [
            SimpleNamespace(
                atom_id=atom_id,
                ai_id="ai",
                owner_type="person",
                owner_id="person",
                lfu_state=LFUState(counter, now.timestamp()).as_dict(),
                importance=0.5,
                confidence=0.5,
                created_at=now,
                consolidated_at=now if consolidated else None,
            )
            for atom_id, counter, consolidated in (
                (1, 1, True),
                (2, 2, True),
                (3, 3, True),
                (4, 0, False),
            )
        ]
        db = _EvictionDB(atoms)
        lfu = LazyLFU(LFUConfig(10, 10, 5, 255, 20, 10))
        service = MemoryEvictionService(
            db,
            lfu,
            record_capacity_per_owner=10,
            atom_capacity_per_owner=2,
            deletable_reference_count=0,
        )

        evicted = await service.evict_atoms_for_ids([4])

        self.assertEqual(2, evicted)
        self.assertEqual([1, 2], db.deleted_ids)


class _EpisodeResult(list):
    def first(self):
        return self[0] if self else None


class _EpisodeLFUDB:
    def __init__(self, atoms) -> None:
        self.atoms = atoms
        self.atom_updates = 0

    def session(self):
        return _EpisodeLFUSession(self)


class _EpisodeLFUSession:
    def __init__(self, db: _EpisodeLFUDB) -> None:
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        sql = str(statement).lower()
        if sql.startswith("update memory_atoms"):
            self._db.atom_updates += 1
            return _EpisodeResult()
        if "from conversations" in sql or "from messages" in sql:
            return _EpisodeResult([(True,)])
        if "from memory_atoms" in sql and "join conversation_episodes" in sql:
            return _EpisodeResult(self._db.atoms)
        if "from memory_atoms" in sql:
            selected_ids = next(value for value in statement.compile().params.values() if isinstance(value, list))
            return _EpisodeResult([row for row in self._db.atoms if row.atom_id in selected_ids])
        if "from conversation_summaries" in sql:
            return _EpisodeResult([SimpleNamespace(summary="摘要")])
        return _EpisodeResult()

    async def commit(self) -> None:
        pass


class EpisodeMemoryLFUTests(unittest.IsolatedAsyncioTestCase):
    async def test_person_context_accesses_only_frequency_ranked_results(self) -> None:
        settings = _settings()
        now = datetime.now(timezone.utc)
        atoms = [
            SimpleNamespace(
                atom_id=atom_id,
                content=content,
                memory_type="fact",
                importance=0.5,
                confidence=0.5,
                created_at=now,
                lfu_state=LFUState(counter, now.timestamp()).as_dict(),
            )
            for atom_id, content, counter in (
                (1, "低频", 1),
                (2, "高频", 8),
                (3, "中频", 4),
            )
        ]
        db = _EpisodeLFUDB(atoms)
        repo = EpisodeMemoryRepository(
            db,
            settings.memory,
            LazyLFU(LFUConfig(**settings.lfu.memory.model_dump()), random_value=lambda: 0.0),
        )
        context = ToolExecutionContext(
            ai_id="ai",
            account_id="account",
            conversation_id="789",
            platform="qq",
            chat_type="private",
            chat_id="person",
            sender_person_id="123",
        )

        result = await repo.person_context(context, "123", 2)

        self.assertEqual(["高频", "中频"], [fact["content"] for fact in result["facts"]])
        self.assertEqual(2, db.atom_updates)


if __name__ == "__main__":
    unittest.main()
