
from __future__ import annotations

import hashlib
import json
from typing import Any

from shared.contracts.agent import AgentDefinition, AgentDefinitionError


class NacosAgentDefinitionStore:
    def __init__(self, provider) -> None:
        if provider is None:
            raise AgentDefinitionError("AI 定义必须使用 Nacos ConfigProvider")
        self._provider = provider

    async def load(self, ai_id: str) -> AgentDefinition:
        key = f"agent.{ai_id}"
        data = await self._provider.get(key)
        if not data:
            raise AgentDefinitionError(f"Nacos 缺少 AI 定义: {key}")
        configured_ai_id = str(data.get("ai_id", "")).strip()
        if configured_ai_id != ai_id:
            raise AgentDefinitionError(f"{key} 的 ai_id 必须等于 {ai_id}")
        identity = str(data.get("identity", "")).strip()
        if not identity:
            raise AgentDefinitionError(f"{key} 缺少 identity")
        extensions = data.get("extensions", [])
        if not isinstance(extensions, list):
            raise AgentDefinitionError(f"{key}.extensions 必须是列表")
        prompts = data.get("prompts", {})
        if not isinstance(prompts, dict):
            raise AgentDefinitionError(f"{key}.prompts 必须是对象")
        canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return AgentDefinition(
            ai_id=ai_id,
            version=int(data.get("version", 1)),
            name=str(data.get("name", ai_id)),
            identity=identity,
            personality=self._mapping(data.get("personality")),
            relationship_policy=self._mapping(data.get("relationship_policy")),
            behavior_policy=self._mapping(data.get("behavior_policy")),
            extensions=[dict(item) for item in extensions if isinstance(item, dict)],
            prompts={str(name): str(content).strip() for name, content in prompts.items()},
            model_profile_id=str(data.get("model_profile_id", "default")),
            voice_profile_id=str(data.get("voice_profile_id", "default")),
            avatar_profile_id=str(data.get("avatar_profile_id", "default")),
            model_config=self._mapping(data.get("model_config")),
            definition_key=key,
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    async def list_active(self) -> list[AgentDefinition]:
        catalog = await self._provider.get("agent.catalog")
        ai_ids = catalog.get("active_ai_ids", []) if isinstance(catalog, dict) else []
        if not isinstance(ai_ids, list):
            raise AgentDefinitionError("agent.catalog.active_ai_ids 必须是列表")
        return [await self.load(str(ai_id)) for ai_id in ai_ids]

    @staticmethod
    def _mapping(value) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}
