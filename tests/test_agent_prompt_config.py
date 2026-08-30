import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import yaml

from agent.conversation.message_understanding import MessageUnderstanding
from agent.conversation.prompt_assembler import PromptAssembler
from agent.conversation.response_plan import ParticipationDecision
from agent.social.group_participation_service import GroupParticipationService
from shared.contracts.rpc.relationship import GroupRelationshipData, GroupRelationshipResponse
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.nacos_agent_definition_store import NacosAgentDefinitionStore

ROOT = Path(__file__).resolve().parents[1]


# 提供文件配置提供器相关能力
class FileConfigProvider:
    # 获取数据
    async def get(self, key: str) -> dict:
        path = ROOT / "deploy" / "nacos" / f"{key}.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))


# 验证智能体提示词配置
class AgentPromptConfigTests(unittest.IsolatedAsyncioTestCase):
    # 验证真实配置加载后保留消息分隔符
    async def test_message_separator_survives_real_config_loading(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        prompts = PromptAssembler(definition)
        understanding = MessageUnderstanding(
            prompts,
            {ContentType.TEXT: (lambda _: "扩展内容",)},
            image_describer=object(),
        )

        result = await understanding.understand(
            SocialMessage(
                chat=Chat(chat_id="private", chat_type=ChatType.PRIVATE),
                sender=SocialSender(user_id="2195232218", name="联系人"),
                type=ContentType.TEXT,
                text="晚上好",
            )
        )

        self.assertEqual("\n", definition.prompts["message-separator"])
        self.assertEqual("联系人: 扩展内容\n联系人: 晚上好", result)

    # 验证被点名消息进入群聊参与决策
    async def test_addressed_group_message_reaches_participation_model(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        conversation = SimpleNamespace(
            window=lambda _chat_type, _chat_id: [
                (
                    "user",
                    "联系人: 你还记得群主吗",
                    {"speaker_id": "person", "speaker_name": "联系人"},
                )
            ]
        )
        bus = SimpleNamespace(
            request_model=AsyncMock(
                return_value=GroupRelationshipResponse(
                    relationship=GroupRelationshipData(
                        familiarity=0.0,
                        belonging=0.0,
                        affinity=0.0,
                        activity_willingness=0.0,
                    )
                )
            )
        )
        prompt_assembler = PromptAssembler(definition)
        chat_agent = SimpleNamespace(
            decide_participation=AsyncMock(
                return_value=ParticipationDecision(
                    participate=True,
                    reason="问题明确",
                )
            )
        )
        participation = GroupParticipationService(
            ai_id=definition.ai_id,
            account_id="account",
            bus=bus,
            relationship_timeout_sec=1.0,
            sessions=object(),
            conversation=conversation,
            persona=SimpleNamespace(name=definition.name),
            prompt_assembler=prompt_assembler,
            chat_agent=chat_agent,
            proactive=definition.behavior_policy.proactive,
            behavior_schedule=SimpleNamespace(allows_proactive=lambda: True),
        )

        result = await participation.should_join("group", explicitly_addressed=True)

        self.assertTrue(result)
        system_prompt, user_prompt = chat_agent.decide_participation.await_args.args
        self.assertIn("当前真实消息明确 @ 了你", user_prompt)
        self.assertIn("[person | 联系人]", user_prompt)
        self.assertIn("联系人: 你还记得群主吗", user_prompt)
        self.assertIn("只输出合法 JSON", system_prompt)

    async def test_active_group_topic_uses_relaxed_participation_prompt(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        conversation = SimpleNamespace(
            window=lambda _chat_type, _chat_id: [
                (
                    "user",
                    "联系人: 这个问题你们怎么看",
                    {"speaker_id": "person", "speaker_name": "联系人"},
                )
            ]
        )
        bus = SimpleNamespace(
            request_model=AsyncMock(
                return_value=GroupRelationshipResponse(
                    relationship=GroupRelationshipData(
                        familiarity=0.8,
                        belonging=0.8,
                        affinity=1.0,
                        activity_willingness=0.6,
                    )
                )
            )
        )
        chat_agent = SimpleNamespace(
            decide_participation=AsyncMock(
                return_value=ParticipationDecision(
                    participate=True,
                    reason="有自然切入点",
                )
            )
        )
        participation = GroupParticipationService(
            ai_id=definition.ai_id,
            account_id="account",
            bus=bus,
            relationship_timeout_sec=1.0,
            sessions=object(),
            conversation=conversation,
            persona=SimpleNamespace(name=definition.name),
            prompt_assembler=PromptAssembler(definition),
            chat_agent=chat_agent,
            proactive=definition.behavior_policy.proactive,
            behavior_schedule=SimpleNamespace(allows_proactive=lambda: True),
        )

        participation.observe("group")
        participation.observe("group")
        result = await participation.should_join("group", explicitly_addressed=False)

        self.assertEqual(2, definition.behavior_policy.proactive.group_join_min_messages)
        self.assertTrue(result)
        chat_agent.decide_participation.assert_awaited_once()
        system_prompt, _ = chat_agent.decide_participation.await_args.args
        self.assertIn("不要求一定提供尚未出现的新信息", system_prompt)
        self.assertIn("关系与参与度较高时应适当更主动", system_prompt)


if __name__ == "__main__":
    unittest.main()
