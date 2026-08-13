
from __future__ import annotations

import hashlib
import json
from typing import Any

from shared.contracts.agent import AgentDefinition, AgentDefinitionError
from shared.infrastructure.runtime_config import required_config, required_value


class NacosAgentDefinitionStore:
    def __init__(self, provider) -> None:
        if provider is None:
            raise AgentDefinitionError("AI 定义必须使用 Nacos ConfigProvider")
        self._provider = provider

    async def load(self, ai_id: str) -> AgentDefinition:
        default_key = "agent.default"
        key = f"agent.{ai_id}"
        defaults = await self._provider.get(default_key)
        if not defaults:
            raise AgentDefinitionError(f"Nacos 缺少通用 AI 配置: {default_key}")
        overrides = await self._provider.get(key)
        if not overrides:
            raise AgentDefinitionError(f"Nacos 缺少 AI 定义: {key}")
        data = self._deep_merge(defaults, overrides)
        configured_ai_id = required_value(
            str(required_config(data, "ai_id", f"{key}.ai_id")),
            f"{key}.ai_id",
        )
        if configured_ai_id != ai_id:
            raise AgentDefinitionError(f"{key} 的 ai_id 必须等于 {ai_id}")
        identity = required_value(
            str(required_config(data, "identity", f"{key}.identity")),
            f"{key}.identity",
        )
        extensions = required_config(data, "extensions", f"{key}.extensions")
        if not isinstance(extensions, list):
            raise AgentDefinitionError(f"{key}.extensions 必须是列表")
        for index, extension in enumerate(extensions):
            if not isinstance(extension, dict):
                raise AgentDefinitionError(f"{key}.extensions[{index}] 必须是对象")
        prompts = required_config(data, "prompts", f"{key}.prompts")
        if not isinstance(prompts, dict):
            raise AgentDefinitionError(f"{key}.prompts 必须是对象")
        model_config = self._mapping(
            required_config(data, "model_config", f"{key}.model_config"),
            f"{key}.model_config",
        )
        for tier in ("fast", "standard", "deep"):
            candidates = required_config(model_config, tier, f"{key}.model_config.{tier}")
            if not isinstance(candidates, list):
                raise AgentDefinitionError(f"{key}.model_config.{tier} 必须是列表")
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise AgentDefinitionError(f"{key}.model_config.{tier} 每项必须是对象")
                for field in ("id", "provider", "thinking"):
                    required_config(candidate, field, f"{key}.model_config.{tier}.{field}")
        canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return AgentDefinition(
            ai_id=ai_id,
            version=int(required_config(data, "version", f"{key}.version")),
            name=required_value(str(required_config(data, "name", f"{key}.name")), f"{key}.name"),
            identity=identity,
            personality=self._mapping(required_config(data, "personality", f"{key}.personality"), f"{key}.personality"),
            relationship_policy=self._mapping(required_config(data, "relationship_policy", f"{key}.relationship_policy"), f"{key}.relationship_policy"),
            behavior_policy=self._mapping(required_config(data, "behavior_policy", f"{key}.behavior_policy"), f"{key}.behavior_policy"),
            extensions=[dict(item) for item in extensions],
            prompts={
                str(name): (
                    str(content)
                    if str(name) == "message-separator"
                    else str(content).strip()
                )
                for name, content in prompts.items()
            },
            model_profile_id=required_value(str(required_config(data, "model_profile_id", f"{key}.model_profile_id")), f"{key}.model_profile_id"),
            voice_profile_id=required_value(str(required_config(data, "voice_profile_id", f"{key}.voice_profile_id")), f"{key}.voice_profile_id"),
            avatar_profile_id=required_value(str(required_config(data, "avatar_profile_id", f"{key}.avatar_profile_id")), f"{key}.avatar_profile_id"),
            model_config=model_config,
            definition_key=key,
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    async def list_active(self) -> list[AgentDefinition]:
        catalog = await self._provider.get("agent.catalog")
        if not catalog:
            raise AgentDefinitionError("Nacos 缺少配置: agent.catalog")
        ai_ids = required_config(catalog, "active_ai_ids", "agent.catalog.active_ai_ids")
        if not isinstance(ai_ids, list):
            raise AgentDefinitionError("agent.catalog.active_ai_ids 必须是列表")
        return [await self.load(str(ai_id)) for ai_id in ai_ids]

    @staticmethod
    def _mapping(value, config_name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise AgentDefinitionError(f"{config_name} 必须是对象")
        return dict(value)

    @classmethod
    def _deep_merge(cls, defaults: dict, overrides: dict) -> dict:
        merged = dict(defaults)
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
