from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from memory.memory_output_policy import MemoryDocumentPolicy, MemoryOutputPolicy
from memory.memory_prompt_assembler import MemoryPromptAssembler
from shared import database_models as m
from shared.agent_definition_store import AgentDefinitionStore
from shared.contracts.memory_output import MemoryConsolidationOutput
from shared.database import Database
from shared.global_settings_store import GlobalSettingsStore
from shared.mounted_config_provider import MountedConfigProvider


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def atom_fingerprint(atom: dict) -> str:
    fields = ("atom_id", "ai_id", "owner_type", "owner_id", "content", "source_message_ids", "consolidated_at")
    return digest({key: atom[key] for key in fields})


class SelfMemoryRepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id: str
    expected_version: int
    expected_document_sha256: str
    expected_atoms: dict[str, str]
    markdown: str = Field(min_length=1)

    @classmethod
    def from_snapshot(cls, snapshot: dict, markdown: str) -> SelfMemoryRepairPlan:
        ai_id = snapshot["definition"]["ai_id"]
        document, = [row for row in snapshot["documents"]
                     if (row["ai_id"], row["owner_type"], row["owner_id"]) == (ai_id, "self", ai_id)]
        return cls(
            ai_id=ai_id,
            expected_version=document["version"],
            expected_document_sha256=digest(document["markdown_content"]),
            expected_atoms={str(row["atom_id"]): atom_fingerprint(row) for row in snapshot["atoms"]
                            if (row["ai_id"], row["owner_type"], row["owner_id"]) == (ai_id, "self", ai_id)},
            markdown=markdown,
        )


class SelfMemoryRepair:
    def __init__(self, database, definitions, settings) -> None:
        self._db = database
        self._definitions = definitions
        self._settings = settings

    async def run(self, plan: SelfMemoryRepairPlan, *, apply: bool = False) -> dict:
        definition = await self._definitions.load(plan.ai_id)
        policy = MemoryDocumentPolicy(self._settings.document_schemas)
        anchored = policy.anchor_identity(plan.markdown, MemoryPromptAssembler(definition).persona())
        if anchored != plan.markdown.strip():
            raise ValueError("修订稿核心身份与当前正式配置存在差异")
        MemoryOutputPolicy(self._settings.generation.output_limits).validate_consolidation(
            MemoryConsolidationOutput(markdown=anchored)
        )
        async with self._db.session() as session:
            async with session.begin():
                if not apply:
                    await session.connection(execution_options={"postgresql_readonly": True})
                document_query = select(m.MemoryDocument).where(
                    m.MemoryDocument.ai_id == plan.ai_id, m.MemoryDocument.owner_type == "self",
                    m.MemoryDocument.owner_id == plan.ai_id,
                )
                atoms_query = select(m.MemoryAtom).where(
                    m.MemoryAtom.ai_id == plan.ai_id, m.MemoryAtom.owner_type == "self",
                    m.MemoryAtom.owner_id == plan.ai_id,
                ).order_by(m.MemoryAtom.atom_id)
                if apply:
                    document_query = document_query.with_for_update()
                    atoms_query = atoms_query.with_for_update()
                document = (await session.execute(document_query)).scalar_one()
                atoms = (await session.execute(atoms_query)).scalars().all()
                current = {str(atom.atom_id): atom_fingerprint({
                    column.key: getattr(atom, column.key) for column in atom.__table__.columns
                }) for atom in atoms}
                if (document.version != plan.expected_version
                        or digest(document.markdown_content) != plan.expected_document_sha256
                        or current != plan.expected_atoms):
                    raise ValueError("自我认知已变化，请基于最新快照复核修订稿")
                if apply:
                    document.markdown_content = anchored
                    document.version += self._settings.document_version_increment
                    document.updated_at = func.now()
                    for atom in atoms:
                        if atom.consolidated_at is None:
                            atom.consolidated_at = func.now()
        return {"applied": apply, "ai_id": plan.ai_id, "baseline_atoms": len(current),
                "version": plan.expected_version + (self._settings.document_version_increment if apply else 0)}


async def _run(args) -> None:
    plan = SelfMemoryRepairPlan.model_validate_json(args.plan.read_text(encoding="utf-8-sig"))
    provider, database = MountedConfigProvider(), Database()
    try:
        await provider.connect()
        await database.connect()
        settings = (await GlobalSettingsStore(provider).load()).memory
        result = await SelfMemoryRepair(database, AgentDefinitionStore(provider), settings).run(plan, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        await database.close()
        await provider.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="核对或应用已审阅的自我认知修订稿；默认只读核对。")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="在记忆插件已暂停并 drain 后应用修订稿")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
