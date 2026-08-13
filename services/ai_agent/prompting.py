
from __future__ import annotations

from dataclasses import dataclass, field

from shared.contracts.agent import AgentDefinition


RESPONSE_PLAN_INSTRUCTION = """请只输出一个 JSON 对象：
{
  "speech": [{"text": "真正要说的话", "delivery": "text|voice|live"}],
  "emotion": {"name": "neutral|happy|sad|angry|surprised", "intensity": 0.0},
  "actions": [{"type": "sticker|avatar_motion", "query": "可选"}],
  "tool_calls": [],
  "memory_candidates": []
}
不要在 speech.text 中加入【语音】、【表情】等控制标记。"""


@dataclass(frozen=True)
class PromptContext:
    scene: str
    user_input: str
    relationship_summary: str = ""
    memories: tuple[str, ...] = ()
    growth_summary: str = ""
    global_state: str = ""
    scene_state: str = ""
    recent_messages: tuple[str, ...] = ()
    tool_summary: str = ""
    director_instruction: str = ""
    output_protocol: str = RESPONSE_PLAN_INSTRUCTION
    extra: dict[str, str] = field(default_factory=dict)


class PromptAssembler:
    def __init__(self, definition: AgentDefinition) -> None:
        self._definition = definition

    def build_system_prompt(self, context: PromptContext) -> str:
        personality = self._definition.personality
        traits = "、".join(str(item) for item in personality.get("traits", []))
        speaking_style = str(personality.get("speaking_style", "自然、口语化"))
        catchphrases = "、".join(str(item) for item in personality.get("catchphrases", []))
        taboos = "、".join(str(item) for item in personality.get("taboos", []))
        scene_template = self._definition.prompts.get(context.scene, "")

        sections = [
            self._section("稳定身份", self._definition.identity),
            self._section(
                "人格表达",
                f"性格：{traits or '按稳定身份自然表达'}\n"
                f"说话风格：{speaking_style}\n"
                f"口头习惯：{catchphrases or '无固定要求'}\n"
                f"禁忌：{taboos or '无额外项'}",
            ),
            self._section("长期成长", context.growth_summary),
            self._section("当前关系", context.relationship_summary),
            self._section("相关记忆", "\n".join(f"- {item}" for item in context.memories)),
            self._section("当前状态", "\n".join(item for item in (context.global_state, context.scene_state) if item)),
            self._section("场景规则", scene_template),
            self._section("导演指令", context.director_instruction),
            self._section("可用工具", context.tool_summary),
            self._section("输出协议", context.output_protocol),
        ]
        return "\n\n".join(section for section in sections if section)

    def build_user_prompt(self, context: PromptContext) -> str:
        recent = "\n".join(context.recent_messages)
        if recent:
            return f"最近对话：\n{recent}\n\n本轮消息：\n{context.user_input}"
        return context.user_input

    @staticmethod
    def _section(title: str, content: str) -> str:
        value = content.strip()
        return f"## {title}\n{value}" if value else ""
