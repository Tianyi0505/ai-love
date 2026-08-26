from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from nats.js.errors import KeyNotFoundError, KeyWrongLastSequenceError, NoKeysError

from agent.memory_client import MemoryClient
from agent.prompt_assembler import PromptAssembler, PromptContext
from memory.memory_output_policy import MemoryDocumentPolicy, MemoryDocumentSchemas
from memory.memory_state_store import MemoryStateStore
from shared.contracts.agent import AgentDefinition, ModelSelectionConfig, PersonalityConfig
from shared.contracts.memory import MemoryActivity
from shared.global_settings import MemoryConsolidationSettings


# 提供测试用状态条目
@dataclass
class FakeEntry:
    value: bytes
    revision: int


# 提供测试用键值存储
class FakeKV:
    # 初始化当前实例
    def __init__(self) -> None:
        self._values: dict[str, FakeEntry] = {}
        self._revision = 0

    # 列出全部键
    async def keys(self):
        if not self._values:
            raise NoKeysError
        return list(self._values)

    # 获取数据
    async def get(self, key: str):
        if key not in self._values:
            raise KeyNotFoundError
        return self._values[key]

    # 创建实例
    async def create(self, key: str, value: bytes):
        if key in self._values:
            raise KeyWrongLastSequenceError
        return self._write(key, value)

    # 更新数据
    async def update(self, key: str, value: bytes, last: int):
        if key not in self._values or self._values[key].revision != last:
            raise KeyWrongLastSequenceError
        return self._write(key, value)

    # 删除数据
    async def delete(self, key: str, last: int):
        if key not in self._values or self._values[key].revision != last:
            raise KeyWrongLastSequenceError
        del self._values[key]

    # 写入数据
    def _write(self, key: str, value: bytes) -> int:
        self._revision += 1
        self._values[key] = FakeEntry(value, self._revision)
        return self._revision

    # 列出全部值
    def values(self) -> list[dict]:
        return [json.loads(entry.value) for entry in self._values.values()]


# 提供测试用消息总线
class FakeBus:
    # 初始化当前实例
    def __init__(self) -> None:
        self.published = []

    # 向持久化主题发布JSON消息
    async def publish_durable_model(self, subject: str, payload) -> None:
        self.published.append((subject, payload.model_dump(mode="json")))


# 验证记忆任务状态管理
class MemoryStateTests(unittest.IsolatedAsyncioTestCase):
    # 准备异步测试环境
    async def asyncSetUp(self) -> None:
        self.activity = FakeKV()
        self.pending = FakeKV()
        self.state = MemoryStateStore(self.activity, self.pending, 10, 30, 8)

    # 验证多条消息只保留最新静默检查
    async def test_many_messages_keep_only_latest_quiet_check(self) -> None:
        for sequence in range(1, 101):
            await self.state.record_activity(
                MemoryActivity(
                    ai_id="ai",
                    person_id="person",
                    conversation_id="conversation",
                    message_id=str(sequence),
                    sequence=sequence,
                    active_at=float(sequence),
                )
            )
        self.assertEqual(1, len(self.activity.values()))
        self.assertEqual(100, self.activity.values()[0]["sequence"])
        self.assertEqual([], await self.state.due_activities(now=109))
        self.assertEqual(1, len(await self.state.due_activities(now=110)))

    # 验证新活动使在途静默检查失效
    async def test_new_activity_invalidates_in_flight_quiet_check(self) -> None:
        await self.state.record_activity(
            MemoryActivity(
                ai_id="ai",
                person_id="person",
                conversation_id="conversation",
                message_id="old",
                sequence=1,
                active_at=1,
            )
        )
        claim = await self.state.claim_activity((await self.state.due_activities(now=11))[0], now=11)
        await self.state.record_activity(
            MemoryActivity(
                ai_id="ai",
                person_id="person",
                conversation_id="conversation",
                message_id="new",
                sequence=2,
                active_at=12,
            )
        )
        await self.state.finish_activity(claim)
        self.assertEqual("new", self.activity.values()[0]["message_id"])

    # 验证新记忆原子不被旧批次删除
    async def test_new_pending_atoms_survive_completed_batch(self) -> None:
        await self.state.add_pending("ai", "person", "person", "episode-1", ["atom-1"], 10, 1)
        ready = await self.state.ready_pending(
            MemoryConsolidationSettings.model_validate(
                {
                    "scheduler_poll_sec": 1,
                    "person": {
                        "min_episode_count": 1,
                        "min_atom_count": 10,
                        "token_threshold": 100,
                        "max_wait_sec": 100,
                    },
                    "self": {
                        "min_episode_count": 10,
                        "min_atom_count": 10,
                        "token_threshold": 100,
                        "max_wait_sec": 100,
                    },
                }
            ),
            now=2,
        )
        claim = await self.state.claim_pending(ready[0], now=2)
        await self.state.add_pending("ai", "person", "person", "episode-2", ["atom-2"], 20, 3)
        await self.state.complete_pending(claim)
        value = self.pending.values()[0]
        self.assertEqual(["atom-2"], value["atom_ids"])
        self.assertEqual(["episode-2"], value["episode_ids"])

    # 验证重构前写入的派生计数字段不阻断待合并任务恢复
    async def test_legacy_pending_counters_are_ignored(self) -> None:
        await self.pending.create(
            "pending.legacy",
            json.dumps(
                {
                    "ai_id": "ai",
                    "owner_type": "person",
                    "owner_id": "person",
                    "episode_ids": ["episode-1"],
                    "atom_ids": ["atom-1"],
                    "episode_tokens": {"episode-1": 10},
                    "episode_count": 1,
                    "atom_count": 1,
                    "estimated_tokens": 10,
                    "first_pending_at": 1,
                    "status": "active",
                    "lease_until": 0,
                    "claim_id": "",
                }
            ).encode(),
        )
        ready = await self.state.ready_pending(
            MemoryConsolidationSettings.model_validate(
                {
                    "scheduler_poll_sec": 1,
                    "person": {
                        "min_episode_count": 1,
                        "min_atom_count": 10,
                        "token_threshold": 100,
                        "max_wait_sec": 100,
                    },
                    "self": {
                        "min_episode_count": 10,
                        "min_atom_count": 10,
                        "token_threshold": 100,
                        "max_wait_sec": 100,
                    },
                }
            ),
            now=2,
        )
        self.assertEqual("pending.legacy", ready[0].key)

    # 验证记忆客户端只发布轻量活动
    async def test_agent_memory_client_only_publishes_lightweight_activity(self) -> None:
        bus = FakeBus()
        client = MemoryClient(bus, "ai", {}, {"memory_context_sec": 1})
        await client.activity(
            person_id="person",
            conversation_id="conversation",
            message_id="message",
        )
        self.assertEqual(1, len(bus.published))
        subject, payload = bus.published[0]
        self.assertEqual("memory.activity", subject)
        self.assertEqual("ai", payload["ai_id"])
        self.assertNotIn("memories", payload)


# 验证记忆文档渲染
class MemoryDocumentTests(unittest.TestCase):
    # 验证未配置标题被明确拒绝
    def test_document_rejects_unknown_sections(self) -> None:
        policy = MemoryDocumentPolicy(
            MemoryDocumentSchemas.model_validate(
                {
                    "person": {
                        "title": "联系人长期认知",
                        "sections": ["稳定偏好", "不确定信息"],
                        "empty_document": "# 联系人长期认知",
                    },
                    "self": {
                        "title": "自我长期认知",
                        "sections": ["稳定偏好", "不确定信息"],
                        "empty_document": "# 自我长期认知",
                    },
                }
            )
        )
        markdown = """# 联系人长期认知
## 稳定偏好
- 喜欢纵向流程图
- 喜欢先讲代码执行流程
- 不喜欢箭头指向箭头
## 模型自创标题
- 来源还不确定
"""
        with self.assertRaises(ValueError):
            policy.validate("person", markdown)

    # 验证提示词包含身份关系摘要和当前消息
    def test_prompt_contains_self_person_summary_and_current_message_layers(self) -> None:
        definition = AgentDefinition.model_construct(
            ai_id="ai",
            version=1,
            name="AI",
            identity="identity",
            personality=PersonalityConfig(
                traits=[],
                speaking_style="style",
                catchphrases=[],
                taboos=[],
            ),
            relationship_policy={},
            behavior_policy={},
            extensions=[],
            prompts={
                "system": "${identity}|${self_document}|${person_document}|${conversation_summary}|${relationship_summary}|${memories}|${scene_template}|${tool_summary}|${output_protocol}|${traits}|${speaking_style}|${catchphrases}",
                "social-private": "scene",
                "response-plan": "protocol",
                "user": "current:${user_input}",
                "user-with-history": "history:${recent}|current:${user_input}",
            },
            model_profile_id="default",
            voice_profile_id="default",
            avatar_profile_id="default",
            model_profile=ModelSelectionConfig(model="test:model"),
            definition_key="agent.ai",
            fingerprint="1",
        )
        assembler = PromptAssembler(definition)
        context = PromptContext(
            scene="social-private",
            user_input="现在",
            self_document="self.md",
            person_document="person.md",
            conversation_summary="历史摘要",
            recent_messages=("上一句",),
        )
        system = assembler.build_system_prompt(context)
        user = assembler.build_user_prompt(context)
        self.assertIn("self.md", system)
        self.assertIn("person.md", system)
        self.assertIn("历史摘要", system)
        self.assertEqual("history:上一句|current:现在", user)


if __name__ == "__main__":
    unittest.main()
