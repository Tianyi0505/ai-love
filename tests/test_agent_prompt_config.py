from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import yaml

from agent.application.proactive import GroupChatManager
from agent.context.understanding import MessageUnderstanding
from agent.generation.prompting import PromptAssembler
from agent.runtime import AIRuntime
from shared.contracts.social import Chat, ChatType, ContentType, SocialMessage, SocialSender
from shared.infrastructure.agent_store import NacosAgentDefinitionStore


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
        understanding = MessageUnderstanding(prompts, {})
        understanding.register_handler(ContentType.TEXT, lambda _: "扩展内容")

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
        runtime = object.__new__(AIRuntime)
        runtime.ai_id = definition.ai_id
        runtime._proactive_enabled = True
        runtime._proactive_config = {
            "group_join_min_messages": 2,
            "group_join_history_messages": 5,
            "group_min_score": 0.08,
            "group_participation_weights": {
                "activity_willingness": 0.4,
                "belonging": 0.25,
                "affinity": 0.2,
                "familiarity": 0.15,
            },
        }
        runtime.group_manager = GroupChatManager()
        runtime.conversation = SimpleNamespace(
            window=lambda _chat_type, _chat_id: [
                ("user", "联系人: 你还记得群主吗", {"speaker_name": "联系人"})
            ]
        )
        runtime._group_relationship = AsyncMock(return_value={})
        runtime.prompt_assembler = PromptAssembler(definition)
        runtime.agent_loop = SimpleNamespace(
            run=AsyncMock(return_value='{"participate": true, "reason": "问题明确"}')
        )

        result = await runtime._join_group_checker("group", explicitly_addressed=True)

        self.assertTrue(result)
        messages = runtime.agent_loop.run.await_args.args[0]
        self.assertIn("当前真实消息明确 @ 了你", messages[1].content)
        self.assertIn("[联系人]", messages[1].content)
        self.assertIn("联系人: 你还记得群主吗", messages[1].content)


if __name__ == "__main__":
    unittest.main()
