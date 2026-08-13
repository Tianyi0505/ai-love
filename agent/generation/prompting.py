
from __future__ import annotations

from dataclasses import dataclass, field
from string import Template

from shared.contracts.agent import AgentDefinition


# 表示提示词上下文数据
@dataclass(frozen=True)
class PromptContext:
    scene: str
    user_input: str
    relationship_summary: str = ""
    memories: tuple[str, ...] = ()
    self_document: str = ""
    person_document: str = ""
    conversation_summary: str = ""
    growth_summary: str = ""
    recent_messages: tuple[str, ...] = ()
    tool_summary: str = ""
    output_protocol: str = ""
    extra: dict[str, str] = field(default_factory=dict)


# 组装智能体提示词
class PromptAssembler:
    # 初始化当前实例
    def __init__(self, definition: AgentDefinition) -> None:
        self._definition = definition

    # 构建系统提示词
    def build_system_prompt(self, context: PromptContext) -> str:
        personality = self._definition.personality
        traits = "、".join(str(item) for item in personality["traits"])
        speaking_style = str(personality["speaking_style"])
        catchphrases = "、".join(str(item) for item in personality["catchphrases"])
        return self.render(
            "system",
            identity=self._definition.identity,
            traits=traits,
            speaking_style=speaking_style,
            catchphrases=catchphrases,
            growth_summary=context.growth_summary,
            self_document=context.self_document or context.growth_summary,
            person_document=context.person_document,
            conversation_summary=context.conversation_summary,
            relationship_summary=context.relationship_summary,
            memories="\n".join(f"- {item}" for item in context.memories),
            scene_template=self.template(context.scene),
            tool_summary=context.tool_summary,
            output_protocol=context.output_protocol or self.template("response-plan"),
        ).strip()

    # 构建用户提示词
    def build_user_prompt(self, context: PromptContext) -> str:
        recent = "\n".join(context.recent_messages)
        if recent:
            return self.render("user-with-history", recent=recent, user_input=context.user_input)
        return self.render("user", user_input=context.user_input)

    # 获取提示词模板
    def template(self, key: str) -> str:
        try:
            value = self._definition.prompts[key]
        except KeyError as exc:
            raise RuntimeError(
                f"未配置 {self._definition.definition_key}.prompts.{key}"
            ) from exc
        if not value:
            raise RuntimeError(f"{self._definition.definition_key}.prompts.{key} 不能为空")
        return value

    # 渲染提示词模板
    def render(self, key: str, **values) -> str:
        try:
            return Template(self.template(key)).substitute(
                {name: str(value) for name, value in values.items()}
            )
        except KeyError as exc:
            raise RuntimeError(
                f"{self._definition.definition_key}.prompts.{key} 缺少模板变量 {exc.args[0]}"
            ) from exc
