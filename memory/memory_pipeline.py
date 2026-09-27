from __future__ import annotations

import asyncio
import json
import logging
from string import Template
from typing import cast

from memory.memory_generation_output import (
    MemoryConsolidationOutput,
    MemoryExtractionOutput,
    MemoryOwnerType,
)
from memory.memory_output_policy import MemoryDocumentPolicy, MemoryOutputPolicy
from memory.memory_state_store import ActivityState, PendingState, StateEntry
from shared.global_settings import MemorySettings

logger = logging.getLogger("ailove.memory.pipeline")


# 提取并聚合长期记忆
class MemoryPipeline:
    """提取静默片段并批量更新长期记忆文档"""

    # 初始化当前实例
    def __init__(
        self,
        *,
        repo,
        state,
        models,
        bus,
        config: MemorySettings,
        output_policy: MemoryOutputPolicy,
        document_policy: MemoryDocumentPolicy,
        eviction=None,
    ) -> None:
        self._repo = repo
        self._state = state
        self._models = models
        self._bus = bus
        self._extraction = config.extraction
        self._consolidation = config.consolidation
        self._token_estimation = config.token_estimation
        self._output_policy = output_policy
        self._document_policy = document_policy
        self._eviction = eviction
        self._semaphore = asyncio.Semaphore(config.worker_concurrency)

    # 处理当前到期活动
    async def process_due_activities(self) -> None:
        claims = [
            claim
            for entry in await self._state.due_activities()
            if (claim := await self._state.claim_activity(entry)) is not None
        ]
        await asyncio.gather(*(self._extract_claim(claim) for claim in claims))

    # 处理当前待聚合记忆
    async def process_ready_consolidations(self) -> None:
        claims = [
            claim
            for entry in await self._state.ready_pending(self._consolidation)
            if (claim := await self._state.claim_pending(entry)) is not None
        ]
        await asyncio.gather(*(self._consolidate_claim(claim) for claim in claims))

    # 处理已领取的记忆提取任务
    async def _extract_claim(self, claim: StateEntry[ActivityState]) -> None:
        async with self._semaphore:
            try:
                await self._extract(claim)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[memory] Episode 提取失败: ai=%s person=%s",
                    claim.data.ai_id,
                    claim.data.person_id,
                )
                await self._state.release_activity(claim, self._extraction.retry_delay_sec)
                raise

    # 从会话片段提取记忆
    async def _extract(self, claim: StateEntry[ActivityState]) -> None:
        data = claim.data
        messages = await self._repo.load_episode_messages(
            data.ai_id,
            data.person_id,
            data.conversation_id,
            data.active_at,
        )
        if not messages:
            await self._state.finish_activity(claim)
            return
        definition, _ = await self._models.resources(data.ai_id)
        conversation = "\n".join(
            f"[{item.person_id + ' | ' if item.person_id else ''}{item.speaker if item.role == 'user' else definition.name}] {item.text}"
            for item in messages
        )
        prompt = Template(definition.prompts["memory-extraction"]).substitute(
            ai_name=definition.name,
            person_name=next(
                (item.speaker for item in messages if item.role == "user"),
                "联系人",
            ),
            conversation=conversation,
        )
        output = self._output_policy.validate_extraction(
            await self._models.generate(
                data.ai_id,
                prompt,
                MemoryExtractionOutput,
            )
        )
        summary = output.episode_summary
        atoms = [memory.model_dump(mode="json") for memory in output.memories]
        estimated_tokens = max(
            self._token_estimation.minimum_tokens,
            (len(conversation) + len(summary)) // self._token_estimation.characters_per_token,
        )
        record = await self._repo.save_extraction(
            activity_id=data.activity_id,
            ai_id=data.ai_id,
            person_id=data.person_id,
            conversation_id=data.conversation_id,
            messages=messages,
            summary=summary,
            atoms=atoms,
            estimated_tokens=estimated_tokens,
        )
        all_atom_ids = [atom_id for atom_ids in record.atom_ids_by_owner.values() for atom_id in atom_ids]
        for (owner_type, owner_id), atom_ids in record.atom_ids_by_owner.items():
            owner_tokens = max(
                self._token_estimation.minimum_tokens,
                (len(summary) + sum(len(atom["content"]) for atom in atoms if atom["owner_type"] == owner_type))
                // self._token_estimation.characters_per_token,
            )
            await self._state.add_pending(
                data.ai_id,
                owner_type,
                owner_id,
                record.episode_id,
                atom_ids,
                owner_tokens,
            )
        if self._eviction is not None:
            await self._eviction.evict_atoms_for_ids(all_atom_ids)
        await self._state.finish_activity(claim)
        logger.info(
            "[memory] Episode 已提取: ai=%s person=%s messages=%s atoms=%s",
            data.ai_id,
            data.person_id,
            len(messages),
            len(all_atom_ids),
        )

    # 处理已领取的记忆聚合任务
    async def _consolidate_claim(self, claim: StateEntry[PendingState]) -> None:
        async with self._semaphore:
            try:
                await self._consolidate(claim)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[memory] Markdown 合并失败: ai=%s owner=%s:%s",
                    claim.data.ai_id,
                    claim.data.owner_type,
                    claim.data.owner_id,
                )
                await self._state.release_pending(claim, self._consolidation.retry_delay_sec)
                raise

    # 聚合长期记忆
    async def _consolidate(self, claim: StateEntry[PendingState]) -> None:
        data = claim.data
        owner_type = cast(MemoryOwnerType, data.owner_type)
        document, atoms, summaries = await self._repo.consolidation_input(
            data.ai_id,
            owner_type,
            data.owner_id,
            list(data.episode_ids),
            list(data.atom_ids),
        )
        if not atoms:
            await self._state.complete_pending(claim)
            return
        definition, _ = await self._models.resources(data.ai_id)
        current = document.markdown or self._document_policy.empty_document(owner_type)
        prompt_key = f"memory-{owner_type}-consolidation"
        prompt = Template(definition.prompts[prompt_key]).substitute(
            current_markdown=current,
            episode_summaries=json.dumps(summaries, ensure_ascii=False),
            memory_atoms=json.dumps(atoms, ensure_ascii=False, default=str),
        )
        output = self._output_policy.validate_consolidation(
            await self._models.generate(
                data.ai_id,
                prompt,
                MemoryConsolidationOutput,
            )
        )
        markdown = self._document_policy.validate(owner_type, output.markdown)
        changed = markdown != self._document_policy.validate(owner_type, current)
        version = document.version
        if changed:
            version = await self._repo.save_document(
                data.ai_id,
                owner_type,
                data.owner_id,
                markdown,
                document.version,
            )
        await self._repo.mark_atoms_consolidated(list(data.atom_ids))
        if self._eviction is not None:
            await self._eviction.evict_atoms_for_ids(list(data.atom_ids))
        await self._state.complete_pending(claim)
        logger.info(
            "[memory] Markdown 合并完成: ai=%s owner=%s:%s changed=%s version=%s atoms=%s",
            data.ai_id,
            owner_type,
            data.owner_id,
            changed,
            version,
            len(atoms),
        )
