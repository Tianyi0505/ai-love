from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from output_fixtures import ValidatingOutputClient, tool_call
from sqlalchemy import select
from test_memory_state import FakeKV

from memory.episode_memory_repository import EpisodeMemoryRepository
from memory.memory_generation_output import MemoryAtomOutput, MemoryConsolidationOutput, MemoryExtractionOutput
from memory.memory_model_pool import MemoryModelPool
from memory.memory_output_policy import MemoryDocumentPolicy, MemoryOutputPolicy
from memory.memory_pipeline import MemoryPipeline
from memory.memory_state_store import MemoryStateStore
from shared import database_models as m
from shared.agent_definition_store import AgentDefinitionStore
from shared.contracts.memory import MemoryActivity
from shared.global_settings import GlobalSettings


class FileConfiguration:
    async def get(self, key):
        path = Path(__file__).parents[1] / "deploy/config" / f"{key}.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if key == "ailove.config":
            data["qq"]["whitelist"] = []
        return data


class RecordingModel:
    def __init__(self, extraction):
        self.extraction = extraction
        self.requests = []

    def bind_tools(self, tools, *, tool_choice):
        async def invoke(messages):
            self.requests.append(messages)
            if tool_choice == "submit_memory_extraction":
                output = self.extraction
            elif "联系人长期认知" in messages[-1].content:
                output = MemoryConsolidationOutput(markdown="# 联系人长期认知\n\n## 稳定偏好\n- 喜欢文字步骤。")
            else:
                output = MemoryConsolidationOutput(
                    markdown="# 自我长期认知\n\n## 核心身份\n- 我是服务器住客，没有主人。\n\n"
                    "## 重要经历\n- 在一次聊天中帮联系人整理排查思路。"
                )
            return tool_call(output)

        return RunnableLambda(invoke)


@pytest_asyncio.fixture
async def memory_flow(private_database):
    db = private_database
    async with db.engine.begin() as connection:
        for model in (m.ConversationEpisode, m.MemoryAtom, m.MemoryDocument, m.ConversationSummary):
            await connection.run_sync(model.__table__.create)
    occurred = datetime.fromtimestamp(time.time() - 120, tz=timezone.utc)
    texts = (
        (101, "user", "你部署在哪里？"),
        (102, "assistant", "我跑在免费服务器上，是不懂运维的住客。"),
        (103, "user", "我更喜欢文字步骤，帮我整理这次排查思路好吗？"),
        (104, "assistant", "可以，先看具体错误，再缩小复现范围。"),
    )
    async with db.session() as session:
        session.add(m.Person(person_id=1, display_name="联系人"))
        session.add(m.PlatformIdentity(
            identity_id=2, person_id=1, platform="test", account_id="test",
            platform_user_id="test-person", verified_by="test",
        ))
        for message_id, role, content in texts:
            session.add(m.Message(
                message_id=message_id, conversation_id=3, ai_id="ai_luoyu",
                platform_identity_id=2 if role == "user" else None, role=role,
                content={"text": content}, occurred_at=occurred, correlation_id=str(message_id),
            ))
        session.add(m.MemoryDocument(
            memory_document_id=5, ai_id="ai_luoyu", owner_type="self", owner_id="ai_luoyu",
            markdown_content="# 自我长期认知\n\n## 核心身份\n- 旧文档把免费节点当成人设。",
            version=4,
        ))
        await session.commit()
    config = GlobalSettings.model_validate(await FileConfiguration().get("ailove.config"))
    consolidation = config.memory.consolidation.model_copy(update={
        owner: getattr(config.memory.consolidation, owner).model_copy(update={"min_atom_count": 1})
        for owner in ("self", "person")
    })
    memory = config.memory.model_copy(update={"consolidation": consolidation})
    activity, pending = FakeKV(), FakeKV()
    state = MemoryStateStore(activity, pending, quiet_window_sec=1, lease_sec=60, cas_retry_count=8)
    await state.record_activity(MemoryActivity(
        ai_id="ai_luoyu", person_id="1", conversation_id="3", message_id="104",
        sequence=1, active_at=occurred.timestamp() + 1,
    ))

    def build(extraction):
        model = RecordingModel(extraction)
        models = MemoryModelPool(
            AgentDefinitionStore(FileConfiguration()), config.llm, config.observability,
            model_factory=lambda *args, **kwargs: model,
            output_client_factory=lambda ai_id: ValidatingOutputClient(),
        )
        pipeline = MemoryPipeline(
            repo=EpisodeMemoryRepository(db, memory), state=state, models=models, bus=None, config=memory,
            output_policy=MemoryOutputPolicy(memory.generation.output_limits),
            document_policy=MemoryDocumentPolicy(memory.document_schemas),
        )
        return pipeline, model

    return SimpleNamespace(db=db, build=build, state=state, activity=activity, pending=pending, config=config)


def atom(owner, content, sources):
    return MemoryAtomOutput(
        owner_type=owner, type="episodic" if owner == "self" else "fact", content=content,
        importance=0.8, confidence=0.9, source_message_ids=sources,
    )


@pytest.mark.asyncio
async def test_production_pipeline_grounds_sources_and_anchors_identity(memory_flow):
    extraction = MemoryExtractionOutput(episode_summary="聊天中讨论排查思路。", memories=[
        atom("self", "我是免费服务器上的住客。", ["102"]),
        atom("person", "联系人喜欢文字步骤。", ["103"]),
        atom("self", "帮联系人整理了排查思路。", ["103", "104"]),
    ])
    pipeline, model = memory_flow.build(extraction)
    await pipeline.process_due_activities()
    await pipeline.process_ready_consolidations()

    async with memory_flow.db.session() as session:
        atoms = (await session.execute(select(m.MemoryAtom).order_by(m.MemoryAtom.atom_id))).scalars().all()
        documents = (await session.execute(select(m.MemoryDocument))).scalars().all()
    assert len(atoms) == 2
    assert [a.source_message_ids for a in atoms] == [[103], [103, 104]]
    assert all(a.consolidated_at is not None for a in atoms)
    self_document = next(d for d in documents if d.owner_type == "self")
    assert self_document.version == 5
    assert "存在形态为数字形态" in self_document.markdown_content
    assert "真诚、活泼、有自己的判断" in self_document.markdown_content
    assert "整理排查思路" in self_document.markdown_content
    assert "服务器住客" not in self_document.markdown_content
    assert "没有主人" not in self_document.markdown_content
    assert "文字步骤" in next(d for d in documents if d.owner_type == "person").markdown_content
    assert memory_flow.pending.values() == []
    assert memory_flow.activity.values() == []

    for system, user in model.requests:
        assert isinstance(system, SystemMessage) and isinstance(user, HumanMessage)
        assert "存在形态为数字形态" in system.content
        assert "联系人、被引用人物和 AI 的经历各归其主" in system.content
    extraction_prompt = model.requests[0][-1].content
    for message_id, role in (("101", "user"), ("102", "assistant")):
        assert f'"message_id": "{message_id}", "role": "{role}"' in extraction_prompt
    self_prompt = next(messages[-1].content for messages in model.requests[1:] if "自我长期认知" in messages[-1].content)
    assert "旧文档把免费节点当成人设" not in self_prompt
    assert '"source_message_ids": ["103", "104"]' in self_prompt


@pytest.mark.asyncio
async def test_unknown_evidence_retries_without_saving_any_memory(memory_flow):
    output = MemoryExtractionOutput(episode_summary="讨论排查步骤。", memories=[
        atom("self", "声称有来源的条目。", ["103", "999"]),
    ])
    pipeline, _ = memory_flow.build(output)
    with pytest.raises(ValueError, match="本片段之外"):
        await pipeline.process_due_activities()
    async with memory_flow.db.session() as session:
        assert not (await session.execute(select(m.MemoryAtom))).scalars().all()
        assert not (await session.execute(select(m.ConversationEpisode))).scalars().all()
    assert memory_flow.activity.values()[0]["status"] == "active"
    assert memory_flow.pending.values() == []


@pytest.mark.parametrize("heading", ["## 核心身份", "核心身份\n--------"])
def test_identity_projection_removes_all_duplicate_identity_sections(heading):
    data = yaml.safe_load((Path(__file__).parents[1] / "deploy/config/ailove.config.yaml").read_text(encoding="utf-8"))
    data["qq"]["whitelist"] = []
    policy = MemoryDocumentPolicy(GlobalSettings.model_validate(data).memory.document_schemas)
    markdown = f"# 自我长期认知\n\n{heading}\n- 错误身份甲\n\n## 稳定偏好\n- 喜欢简洁的表达。\n\n{heading}\n- 错误身份乙"
    result = policy.anchor_identity(markdown, "正式人物身份")
    assert result.count("## 核心身份") == 1
    assert "错误身份" not in result
    assert "喜欢简洁的表达" in result
    assert result == policy.anchor_identity(result, "正式人物身份")
