import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import yaml

from agent.conversation.message_understanding import MessageUnderstanding
from agent.conversation.multimodal_input import DirectVisionMessageInputBuilder
from agent.conversation.prompt_assembler import PromptAssembler, PromptContext
from agent.conversation.response_plan import ParticipationDecision
from agent.social.group_participation_service import GroupParticipationService
from shared.contracts.rpc.relationship import GroupRelationshipData, GroupRelationshipResponse
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.global_settings import GlobalSettings
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
    # 验证检索上下文位于用户问题前且标签含义写入系统提示词
    async def test_retrieved_context_precedes_user_question_with_documented_xml_tags(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        prompts = PromptAssembler(definition)
        context = PromptContext(
            scene="social-private",
            user_input="现在的问题",
            memories=("检索到的记忆",),
            recent_messages=("最近的对话",),
        )

        system_prompt = prompts.build_system_prompt(context)
        user_prompt = prompts.build_user_prompt(context)

        self.assertIn("`<retrieved_context>`", system_prompt)
        self.assertIn("`<conversation_history>`", system_prompt)
        self.assertIn("`<user_question>`", system_prompt)
        self.assertNotIn("检索到的记忆", system_prompt)
        self.assertLess(user_prompt.index("<conversation_history>"), user_prompt.index("<retrieved_context>"))
        self.assertLess(user_prompt.index("<retrieved_context>"), user_prompt.index("<user_question>"))
        self.assertIn("</retrieved_context>\n\n<user_question>", user_prompt)
        self.assertIn("检索到的记忆", user_prompt)

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

    async def test_legacy_message_understanding_keeps_separate_vision_path(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        describer = SimpleNamespace(
            describe=AsyncMock(return_value=SimpleNamespace(description="旧视觉模型识别结果"))
        )
        understanding = MessageUnderstanding(PromptAssembler(definition), {}, describer)
        message = SocialMessage(
            chat=Chat(chat_id="private", chat_type=ChatType.PRIVATE),
            sender=SocialSender(user_id="contact", name="联系人"),
            type=ContentType.IMAGE,
            media_url="https://example.com/legacy.jpg",
        )

        result = await understanding.understand(message)

        self.assertEqual("联系人: [图片] 旧视觉模型识别结果", result)
        describer.describe.assert_awaited_once_with("https://example.com/legacy.jpg")

    async def test_forwarded_images_keep_sender_attribution(self) -> None:
        definition = await NacosAgentDefinitionStore(FileConfigProvider()).load("ai_luoyu")
        image_fetcher = SimpleNamespace(
            data_urls=AsyncMock(
                return_value=(
                    "data:image/jpeg;base64,YWxpY2Ux",
                    "data:image/jpeg;base64,YWxpY2Uy",
                    "data:image/jpeg;base64,Ym9i",
                )
            )
        )
        understanding = DirectVisionMessageInputBuilder(
            PromptAssembler(definition),
            {},
            image_fetcher,
        )
        message = SocialMessage(
            chat=Chat(chat_id="private", chat_type=ChatType.PRIVATE),
            sender=SocialSender(user_id="sender", name="转发者"),
            type=ContentType.FORWARD,
            sub_messages=[
                SocialMessage(
                    chat=Chat(chat_id="private", chat_type=ChatType.PRIVATE),
                    sender=SocialSender(user_id="alice", name="小爱"),
                    type=ContentType.IMAGE,
                    media_urls=["https://example.com/alice-1.jpg", "https://example.com/alice-2.jpg"],
                ),
                SocialMessage(
                    chat=Chat(chat_id="private", chat_type=ChatType.PRIVATE),
                    sender=SocialSender(user_id="bob", name="小博"),
                    type=ContentType.IMAGE,
                    media_url="https://example.com/bob.jpg",
                ),
            ],
        )

        result = await understanding.build(message)

        self.assertEqual(
            [
                "小爱: [图片1/2]",
                "小爱: [图片2/2]",
                "小博: [图片]",
            ],
            [image.attribution for image in result.images],
        )
        self.assertEqual(
            [
                "https://example.com/alice-1.jpg",
                "https://example.com/alice-2.jpg",
                "https://example.com/bob.jpg",
            ],
            [image.source_url for image in result.images],
        )
        self.assertIn("小爱: [图片1/2]", result.text)
        self.assertIn("小博: [图片]", result.text)

    async def test_default_agent_prioritizes_deepseek_vision_model_group(self) -> None:
        provider = FileConfigProvider()
        definition = await NacosAgentDefinitionStore(provider).load("ai_luoyu")
        global_config = await provider.get("ailove.config")
        global_config["qq"]["whitelist"] = []
        settings = GlobalSettings.model_validate(global_config)

        self.assertEqual("deepseek-v4-flash", definition.model_profile.model_id)
        self.assertEqual("deepseek-v4-flash", definition.model_profile.group_repeat_model_id)
        self.assertEqual(
            ["deepseek-v4-flash-vision-exp"],
            definition.model_profile.multimodal_model_ids,
        )
        selected_model_ids = {
            definition.model_profile.model_id,
            definition.model_profile.group_repeat_model_id,
            *definition.model_profile.multimodal_model_ids,
        }
        self.assertLessEqual(selected_model_ids, settings.llm.models.keys())
        self.assertEqual("DEEPSEEK_API_KEY", settings.llm.models["deepseek-v4-flash"].api_key_env)

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
