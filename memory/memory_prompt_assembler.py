from __future__ import annotations

from string import Template

from shared.contracts.agent import AgentDefinition


class MemoryPromptAssembler:
    """以正式人物配置构造记忆任务的身份基准。"""

    def __init__(self, definition: AgentDefinition) -> None:
        self._definition = definition

    def persona(self) -> str:
        definition = self._definition
        personality = definition.personality
        return Template(definition.prompts["memory-persona"]).substitute(
            ai_name=definition.name,
            identity=definition.identity,
            traits="、".join(personality.traits),
            speaking_style=personality.speaking_style,
            catchphrases="、".join(personality.catchphrases),
            taboos="\n".join(f"- {item}" for item in personality.taboos),
        ).strip()

    def system(self) -> str:
        return Template(self._definition.prompts["memory-system"]).substitute(persona=self.persona()).strip()
