from __future__ import annotations

import pytest
from sqlalchemy import select

from memory.memory_generation_output import MemoryExtractionOutput
from memory.memory_output_policy import MemoryDocumentPolicy
from memory.memory_prompt_assembler import MemoryPromptAssembler
from memory.self_memory_repair import SelfMemoryRepair, SelfMemoryRepairPlan
from shared import database_models as m
from shared.agent_definition_store import AgentDefinitionStore
from tests.test_memory_persona_integrity import FileConfiguration, atom
from tests.test_memory_persona_integrity import memory_flow as memory_flow


async def preparation(flow):
    definitions = AgentDefinitionStore(FileConfiguration())
    definition = await definitions.load("ai_luoyu")
    pipeline, model = flow.build(MemoryExtractionOutput(episode_summary="讨论了排查思路。", memories=[
        atom("self", "帮联系人整理排查思路。", ["103", "104"]),
        atom("person", "联系人喜欢文字步骤。", ["103"]),
    ]))
    await pipeline.process_due_activities()
    async with flow.db.session() as session:
        documents = (await session.execute(select(m.MemoryDocument))).scalars().all()
        atoms = (await session.execute(select(m.MemoryAtom))).scalars().all()
        def dump(row):
            return {column.key: getattr(row, column.key) for column in row.__table__.columns}
        snapshot = {"definition": {"ai_id": definition.ai_id}, "documents": [dump(d) for d in documents],
                    "atoms": [dump(a) for a in atoms]}
    policy = MemoryDocumentPolicy(flow.config.memory.document_schemas)
    draft = policy.anchor_identity("# 自我长期认知\n\n## 重要经历\n- 帮联系人整理过排查思路。",
                                   MemoryPromptAssembler(definition).persona())
    return pipeline, model, SelfMemoryRepair(flow.db, definitions, flow.config.memory), SelfMemoryRepairPlan.from_snapshot(
        snapshot, draft,
    )


async def test_repair_preserves_atoms_and_person_memory_while_draining_old_self_pending(memory_flow):
    pipeline, model, repair, plan = await preparation(memory_flow)
    assert not (await repair.run(plan))["applied"]
    async with memory_flow.db.session() as session:
        document = (await session.execute(select(m.MemoryDocument))).scalar_one()
        assert document.version == 4 and "旧文档" in document.markdown_content
        assert all(a.consolidated_at is None for a in (await session.execute(select(m.MemoryAtom))).scalars())
    assert (await repair.run(plan, apply=True))["version"] == 5
    await pipeline.process_ready_consolidations()
    async with memory_flow.db.session() as session:
        documents = (await session.execute(select(m.MemoryDocument))).scalars().all()
        atoms = (await session.execute(select(m.MemoryAtom))).scalars().all()
    assert next(d for d in documents if d.owner_type == "self").markdown_content == plan.markdown
    assert next(d for d in documents if d.owner_type == "self").version == 5
    assert "文字步骤" in next(d for d in documents if d.owner_type == "person").markdown_content
    assert len(atoms) == 2
    assert all(a.consolidated_at is not None for a in atoms)
    assert len(model.requests) == 2  # extraction + person consolidation; reviewed self atoms remain consumed
    assert memory_flow.pending.values() == []


@pytest.mark.parametrize("change", ["document", "atom"])
async def test_stale_repair_plan_leaves_database_untouched(memory_flow, change):
    _, _, repair, plan = await preparation(memory_flow)
    async with memory_flow.db.session() as session:
        if change == "document":
            row = (await session.execute(select(m.MemoryDocument))).scalar_one()
            row.version += 1
        else:
            row = (await session.execute(select(m.MemoryAtom).where(m.MemoryAtom.owner_type == "self"))).scalar_one()
            row.content = "已有新的修订内容。"
        await session.commit()
    with pytest.raises(ValueError, match="已变化"):
        await repair.run(plan, apply=True)
    async with memory_flow.db.session() as session:
        assert "旧文档" in (await session.execute(select(m.MemoryDocument))).scalar_one().markdown_content
        assert all(a.consolidated_at is None for a in (await session.execute(select(m.MemoryAtom))).scalars())


async def test_repair_requires_current_configured_identity(memory_flow):
    _, _, repair, plan = await preparation(memory_flow)
    forged = plan.model_copy(update={"markdown": "# 自我长期认知\n\n## 核心身份\n我是免费节点住客。"})
    with pytest.raises(ValueError, match="核心身份"):
        await repair.run(forged, apply=True)
