from __future__ import annotations

import json
from dataclasses import dataclass, field
from string import Template
from xml.sax.saxutils import escape

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
    entity_context: str = ""
    relevant_people: str = ""
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
        traits = "、".join(personality.traits)
        speaking_style = personality.speaking_style
        catchphrases = "、".join(personality.catchphrases)
        prompt = self.render(
            "system",
            identity=self._definition.identity,
            traits=traits,
            speaking_style=speaking_style,
            catchphrases=catchphrases,
            taboos="\n".join(f"- {item}" for item in personality.taboos),
            scene_template=self.template(context.scene),
            person_rules=self.optional_template("person-rules"),
            output_protocol=context.output_protocol or self.template("response-plan"),
        ).strip()
        if context.scene in {"social-group", "group-join"}:
            prompt += "\n\n" + self.template("group-message-format")
        return prompt

    # 构建用户提示词
    def build_user_prompt(self, context: PromptContext) -> str:
        if context.scene in {"social-group", "group-join"}:
            return json.dumps(
                {
                    "retrieved_context": {
                        "relationship_context": context.relationship_summary,
                        "relevant_people": json.loads(context.relevant_people) if context.relevant_people else [],
                        "relevant_memory": list(context.memories),
                        "conversation_summary": context.conversation_summary,
                        "entity_context": json.loads(context.entity_context) if context.entity_context else {},
                        "participation_context": context.extra,
                    },
                    "conversation_history": [record for batch in context.recent_messages for record in json.loads(batch)],
                    "user_question": json.loads(context.user_input),
                },
                ensure_ascii=False,
            )
        retrieved_context = self._build_retrieved_context(context)
        recent = escape("\n".join(context.recent_messages))
        user_input = escape(context.user_input)
        if recent:
            return self.render(
                "user-with-history",
                retrieved_context=retrieved_context,
                recent=recent,
                user_input=user_input,
            )
        return self.render(
            "user",
            retrieved_context=retrieved_context,
            user_input=user_input,
        )

    # 将每轮动态检索结果集中到用户问题前
    def _build_retrieved_context(self, context: PromptContext) -> str:
        memories = "\n".join(f"- {item}" for item in context.memories)
        sections = (
            ("Long-Term Self Knowledge", context.self_document or context.growth_summary),
            ("Long-Term Contact Knowledge", context.person_document),
            ("Relationship Context", context.relationship_summary),
            ("Relevant People", context.relevant_people),
            ("Relevant Memory", memories),
            ("Conversation Summary", context.conversation_summary),
            ("Tool Context", context.tool_summary),
            ("Current Entity Context", context.entity_context),
        )
        return "\n\n".join(
            f"[{title}]\n{escape(value)}"
            for title, value in sections
            if value
        )

    # 获取提示词模板
    def template(self, key: str) -> str:
        try:
            value = self._definition.prompts[key]
        except KeyError as exc:
            raise RuntimeError(f"未配置 {self._definition.definition_key}.prompts.{key}") from exc
        if not value:
            raise RuntimeError(f"{self._definition.definition_key}.prompts.{key} 不能为空")
        return value

    # 读取可选模板
    def optional_template(self, key: str) -> str:
        try:
            return self.template(key)
        except RuntimeError:
            return ""

    # 渲染提示词模板
    def render(self, key: str, **values) -> str:
        try:
            return Template(self.template(key)).substitute({name: str(value) for name, value in values.items()})
        except KeyError as exc:
            raise RuntimeError(f"{self._definition.definition_key}.prompts.{key} 缺少模板变量 {exc.args[0]}") from exc
