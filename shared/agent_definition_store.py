from __future__ import annotations

import hashlib
import json

from deepmerge import always_merger

from shared.contracts.agent import AgentDefinition, AgentDefinitionError


class AgentDefinitionStore:
    def __init__(self, provider) -> None:
        self._provider = provider

    async def load(self, ai_id: str) -> AgentDefinition:
        default_key = "agent.default"
        key = f"agent.{ai_id}"
        defaults = await self._provider.get(default_key)
        if not defaults:
            raise AgentDefinitionError(f"Kubernetes 配置 缺少通用 AI 配置: {default_key}")
        overrides = await self._provider.get(key)
        if not overrides:
            raise AgentDefinitionError(f"Kubernetes 配置 缺少 AI 定义: {key}")
        data = always_merger.merge(always_merger.merge({}, defaults), overrides)
        canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        definition = AgentDefinition.model_validate(
            {
                **data,
                "definition_key": key,
                "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            }
        )
        if definition.ai_id != ai_id:
            raise AgentDefinitionError(f"{key} 的 ai_id 必须等于 {ai_id}")
        return definition

    async def list_active(self) -> list[AgentDefinition]:
        catalog = await self._provider.get("agent.catalog")
        if not catalog:
            raise AgentDefinitionError("Kubernetes 配置 缺少配置: agent.catalog")
        ai_ids = catalog["active_ai_ids"]
        return [await self.load(ai_id) for ai_id in ai_ids]
