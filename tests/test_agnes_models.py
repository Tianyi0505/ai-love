from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml
from agentscope.model import OpenAIChatModel
from output_fixtures import ValidatingOutputClient

from agent.conversation.chat_agent import ChatAgent
from agent.conversation.response_output_policy import ResponseOutputPolicy
from memory.memory_generation_output import MemoryExtractionOutput
from memory.memory_model_pool import MemoryModelPool
from shared.agent_definition_store import AgentDefinitionStore
from shared.chat_model_factory import create_chat_model
from shared.global_settings import ChatModelSettings, GlobalSettings

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("agnes-2.5-flash", "agnes-3.0-flash")


def settings() -> GlobalSettings:
    data = yaml.safe_load((ROOT / "deploy/config/ailove.config.yaml").read_text(encoding="utf-8"))
    # Deployment normally replaces this unrelated personal-data placeholder.
    data["qq"]["whitelist"] = []
    return GlobalSettings.model_validate(data)


@pytest.mark.parametrize("model_id", MODELS)
async def test_agnes_chat_and_memory_use_documented_http_contract(monkeypatch, model_id):
    config = settings()
    requests = []
    outputs = {
        "speech": {
            "speech": [{"text": "你好", "delivery": "text"}],
            "emotion": {"name": "happy", "intensity": 0.5},
            "actions": [],
        },
        "participate": {"participate": True, "reason": "被直接提问"},
        "episode_summary": {"episode_summary": "聊了天气", "memories": []},
    }

    def respond(request):
        assert str(request.url) == "https://apihub.agnes-ai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-agnes-key"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == model_id
        assert "max_tokens" in payload
        assert "max_completion_tokens" not in payload
        assert "response_format" not in payload
        assert "parallel_tool_calls" not in payload
        tool = payload["tools"][0]["function"]
        name = tool["name"]
        assert name == "GenerateStructuredOutput"
        output = next(value for key, value in outputs.items() if key in tool["parameters"]["properties"])
        return httpx.Response(200, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 0,
            "model": model_id,
            "choices": [{
                "index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call-test", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(output)},
                }]},
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        })

    class FileConfigProvider:
        async def get(self, key):
            data = yaml.safe_load((ROOT / "deploy/config" / f"{key}.yaml").read_text(encoding="utf-8"))
            if key == "agent.default":
                data["model_config"] = {
                    "model_id": model_id,
                    "group_repeat_model_id": model_id,
                    "multimodal_model_ids": [],
                }
            return data

    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        def make_model(**kwargs):
            kwargs["client_kwargs"]["http_client"] = client
            return OpenAIChatModel(**kwargs)

        monkeypatch.setattr("shared.chat_model_strategy.OpenAIChatModel", make_model)
        definitions = AgentDefinitionStore(FileConfigProvider())
        definition = await definitions.load("ai_luoyu")
        assert not definition.model_profile.multimodal_model_ids
        model = create_chat_model(
            definition.model_profile.model_id, models=config.llm.models,
            max_tokens=config.llm.max_tokens,
            timeout_sec=config.llm.provider_request_timeout_sec, max_retries=0,
        )
        agent = ChatAgent(
            model=model, model_name=model_id, tools=[],
            output_policy=ResponseOutputPolicy(config.llm.output_limits),
            max_requests=config.llm.max_requests,
            participation_max_requests=config.llm.participation_max_requests,
            max_tokens=config.llm.max_tokens, retry_count=0,
            observability=config.observability,
            output_client=ValidatingOutputClient(),
        )
        for allow_tools in (True, False):
            plan = await agent.generate_plan("请简短回复", "你好", allow_tools=allow_tools)
            assert plan.text == "你好"
        decision = await agent.decide_participation("判断是否需要回复", "你好")
        assert decision.participate
        memory = MemoryModelPool(definitions, config.llm, config.observability, lambda ai_id: ValidatingOutputClient())
        result = await memory.generate("ai_luoyu", "总结对话", MemoryExtractionOutput)
        assert result.episode_summary == "聊了天气"

    assert len(requests) == 4
    assert "请简短回复" in str(requests[0]["messages"][0]["content"])
    assert requests[0]["max_tokens"] == config.llm.max_tokens
    assert requests[-1]["max_tokens"] == config.llm.memory_max_tokens


def test_agnes_catalog_only_contains_free_chat_models():
    models = settings().llm.models
    assert {key for key, value in models.items() if value.provider == "agnes"} == set(MODELS)
    for model_id in MODELS:
        assert models[model_id].model == model_id
        assert models[model_id].api_key_env == "AGNES_API_KEY"


@pytest.mark.parametrize("model_id", ["agnes-2.5-pro", "agnes-2.5-pro-beta", "agnes-image-2.5-flash"])
def test_agnes_rejects_paid_and_non_chat_models(monkeypatch, model_id):
    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    with pytest.raises(ValueError, match="仅接入已核对免费的对话模型"):
        create_chat_model(
            model_id, models={model_id: ChatModelSettings(
                provider="agnes", model=model_id,
                base_url="https://apihub.agnes-ai.com/v1", api_key_env="AGNES_API_KEY",
            )}, max_tokens=100, timeout_sec=10, max_retries=0,
        )


def test_agnes_missing_credential_fails_locally(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AGNES_API_KEY"):
        create_chat_model(
            MODELS[0], models=settings().llm.models,
            max_tokens=100, timeout_sec=10, max_retries=0,
        )
