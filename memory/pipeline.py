from __future__ import annotations

import asyncio
import json
import logging
from string import Template

from ai.llm.factory import create_llm
from ai.llm.providers import anthropic_gw, deepseek, ollama
from ai.llm.types import ChatMessage, ChatRequest

from memory.documents import normalize_markdown
from memory.state import StateEntry

logger = logging.getLogger("ailove.memory.pipeline")

MEMORY_TYPES = {
    "observation",
    "fact",
    "belief",
    "feeling",
    "episodic",
    "procedural",
    "commitment",
}


def parse_json_object(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 对象")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型返回结果必须是对象")
    return value


class MemoryModelPool:
    """按 AI 定义复用记忆任务所需的 LLM。"""

    def __init__(self, definitions, llm_config: dict) -> None:
        self._definitions = definitions
        self._llm_config = llm_config
        self._cache: dict[str, tuple[str, object, object]] = {}

    async def resources(self, ai_id: str):
        definition = await self._definitions.load(ai_id)
        cached = self._cache.get(ai_id)
        if cached and cached[0] == definition.fingerprint:
            return definition, cached[1]
        llm = create_llm(definition.model_config, self._llm_config)
        self._cache[ai_id] = (definition.fingerprint, llm, definition)
        return definition, llm

    async def complete(self, ai_id: str, prompt: str) -> str:
        _, llm = await self.resources(ai_id)
        chunks: list[str] = []
        async for chunk in llm.chat(
            ChatRequest(ai_id=ai_id, messages=[ChatMessage(role="user", content=prompt)])
        ):
            if chunk.content:
                chunks.append(chunk.content)
        return "".join(chunks).strip()


class MemoryPipeline:
    """按静默片段提取并批量更新长期记忆文档。"""

    def __init__(self, *, repo, state, models, bus, config: dict, spawn) -> None:
        self._repo = repo
        self._state = state
        self._models = models
        self._bus = bus
        self._extraction = config["extraction"]
        self._consolidation = config["consolidation"]
        self._spawn = spawn
        self._semaphore = asyncio.Semaphore(int(config["worker_concurrency"]))

    async def activity_loop(self) -> None:
        while True:
            for entry in await self._state.due_activities():
                claim = await self._state.claim_activity(entry)
                if claim is not None:
                    self._spawn(self._extract_claim(claim))
            await asyncio.sleep(float(self._extraction["scheduler_poll_sec"]))

    async def consolidation_loop(self) -> None:
        thresholds = {
            "person": dict(self._consolidation["person"]),
            "self": dict(self._consolidation["self"]),
        }
        while True:
            for entry in await self._state.ready_pending(thresholds):
                claim = await self._state.claim_pending(entry)
                if claim is not None:
                    self._spawn(self._consolidate_claim(claim))
            await asyncio.sleep(float(self._consolidation["scheduler_poll_sec"]))

    async def _extract_claim(self, claim: StateEntry) -> None:
        async with self._semaphore:
            try:
                await self._extract(claim)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[memory] Episode 提取失败: ai=%s person=%s",
                    claim.data.get("ai_id"),
                    claim.data.get("person_id"),
                )
                await self._state.release_activity(
                    claim, float(self._extraction["retry_delay_sec"])
                )

    async def _extract(self, claim: StateEntry) -> None:
        data = claim.data
        await self._bus.publish_json("memory.extract", dict(data))
        messages = await self._repo.load_episode_messages(
            data["ai_id"],
            data["person_id"],
            data["conversation_id"],
            float(data["active_at"]),
        )
        if not messages:
            await self._state.finish_activity(claim)
            return
        definition, _ = await self._models.resources(data["ai_id"])
        conversation = "\n".join(
            f"[{item.speaker if item.role == 'user' else definition.name}] {item.text}"
            for item in messages
        )
        prompt = Template(definition.prompts["memory-extraction"]).substitute(
            ai_name=definition.name,
            person_name=next((item.speaker for item in messages if item.role == "user"), "联系人"),
            conversation=conversation,
        )
        result = parse_json_object(await self._models.complete(data["ai_id"], prompt))
        summary = str(result.get("episode_summary") or "").strip()
        atoms = self._parse_atoms(result.get("memories", []))
        estimated_tokens = max(1, (len(conversation) + len(summary)) // 4)
        record = await self._repo.save_extraction(
            activity_id=data["activity_id"],
            ai_id=data["ai_id"],
            person_id=data["person_id"],
            conversation_id=data["conversation_id"],
            messages=messages,
            summary=summary,
            atoms=atoms,
            estimated_tokens=estimated_tokens,
        )
        all_atom_ids = [
            atom_id for atom_ids in record.atom_ids_by_owner.values() for atom_id in atom_ids
        ]
        await self._bus.publish_json(
            "memory.extracted",
            {
                "ai_id": data["ai_id"],
                "person_id": data["person_id"],
                "episode_id": record.episode_id,
                "atom_ids": all_atom_ids,
            },
        )
        await self._bus.publish_json(
            "conversation.summary",
            {
                "ai_id": data["ai_id"],
                "conversation_id": data["conversation_id"],
                "episode_id": record.episode_id,
                "episode_summary": summary,
            },
        )
        for (owner_type, owner_id), atom_ids in record.atom_ids_by_owner.items():
            owner_tokens = max(
                1,
                (len(summary) + sum(len(atom["content"]) for atom in atoms if atom["owner_type"] == owner_type))
                // 4,
            )
            await self._state.add_pending(
                data["ai_id"],
                owner_type,
                owner_id,
                record.episode_id,
                atom_ids,
                owner_tokens,
            )
        await self._state.finish_activity(claim)
        logger.info(
            "[memory] Episode 已提取: ai=%s person=%s messages=%s atoms=%s",
            data["ai_id"],
            data["person_id"],
            len(messages),
            len(all_atom_ids),
        )

    async def _consolidate_claim(self, claim: StateEntry) -> None:
        async with self._semaphore:
            try:
                await self._consolidate(claim)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[memory] Markdown 合并失败: ai=%s owner=%s:%s",
                    claim.data.get("ai_id"),
                    claim.data.get("owner_type"),
                    claim.data.get("owner_id"),
                )
                await self._state.release_pending(claim)

    async def _consolidate(self, claim: StateEntry) -> None:
        data = claim.data
        owner_type = data["owner_type"]
        subject = f"memory.{owner_type}.consolidate"
        await self._bus.publish_json(subject, dict(data))
        document, atoms, summaries = await self._repo.consolidation_input(
            data["ai_id"],
            owner_type,
            data["owner_id"],
            list(data["episode_ids"]),
            list(data["atom_ids"]),
        )
        if not atoms:
            await self._state.complete_pending(claim)
            return
        definition, _ = await self._models.resources(data["ai_id"])
        current = document.markdown or normalize_markdown(owner_type, "")
        prompt_key = f"memory-{owner_type}-consolidation"
        prompt = Template(definition.prompts[prompt_key]).substitute(
            current_markdown=current,
            episode_summaries=json.dumps(summaries, ensure_ascii=False),
            memory_atoms=json.dumps(atoms, ensure_ascii=False, default=str),
        )
        result = parse_json_object(await self._models.complete(data["ai_id"], prompt))
        markdown = normalize_markdown(owner_type, str(result.get("markdown") or current))
        changed = markdown != normalize_markdown(owner_type, current)
        version = document.version
        if changed:
            version = await self._repo.save_document(
                data["ai_id"],
                owner_type,
                data["owner_id"],
                markdown,
                document.version,
            )
        await self._state.complete_pending(claim)
        logger.info(
            "[memory] Markdown 合并完成: ai=%s owner=%s:%s changed=%s version=%s atoms=%s",
            data["ai_id"],
            owner_type,
            data["owner_id"],
            changed,
            version,
            len(atoms),
        )

    @staticmethod
    def _parse_atoms(raw_memories) -> list[dict]:
        if not isinstance(raw_memories, list):
            return []
        result = []
        for raw in raw_memories:
            if not isinstance(raw, dict):
                continue
            content = str(raw.get("content") or "").strip()
            if not content:
                continue
            memory_type = str(raw.get("type") or raw.get("memory_type") or "observation")
            owner_type = str(raw.get("owner_type") or "person")
            if owner_type not in {"person", "self"}:
                owner_type = "person"
            result.append(
                {
                    "owner_type": owner_type,
                    "type": memory_type if memory_type in MEMORY_TYPES else "observation",
                    "content": content,
                    "importance": MemoryPipeline._unit(raw.get("importance", 0.5)),
                    "confidence": MemoryPipeline._unit(raw.get("confidence", 0.7)),
                }
            )
        return result

    @staticmethod
    def _unit(value) -> float:
        number = float(value)
        if number > 1:
            number /= 100.0
        return max(0.0, min(1.0, number))
