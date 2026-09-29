from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, create_model

from shared.contracts.memory_output import MemoryConsolidationOutput, MemoryExtractionOutput
from shared.contracts.response_output import ParticipationDecision, ResponsePlan
from shared.contracts.vision_output import ImageDescription, StickerDecision


class GroupRepeatDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeat: bool
    reason: str


@dataclass(frozen=True)
class OutputTool:
    name: str
    description: str
    output_type: type[BaseModel]
    arguments_type: type[BaseModel]

    @classmethod
    def define(cls, name: str, description: str, output_type: type[BaseModel]) -> OutputTool:
        arguments = create_model(
            f"{output_type.__name__}Submission",
            __config__=ConfigDict(extra="forbid"),
            result=(output_type, ...),
        )
        return cls(name, description, output_type, arguments)

    def model_tool(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.arguments_type.model_json_schema(),
        }


OUTPUT_TOOLS = (
    OutputTool.define("submit_response_plan", "提交本轮完整回复、情绪与动作结论。", ResponsePlan),
    OutputTool.define("submit_participation_decision", "提交群聊参与结论和简短依据。", ParticipationDecision),
    OutputTool.define("submit_repeat_decision", "提交群聊复读适用性结论和简短依据。", GroupRepeatDecision),
    OutputTool.define("submit_image_description", "提交图片主要用途、可见内容和表情素材分类。", ImageDescription),
    OutputTool.define("submit_sticker_decision", "提交候选图片分类与本轮表情适用性结论。", StickerDecision),
    OutputTool.define("submit_memory_extraction", "提交会话摘要与有消息来源的原子记忆。", MemoryExtractionOutput),
    OutputTool.define("submit_memory_document", "提交整理完成的长期认知文档。", MemoryConsolidationOutput),
)
OUTPUT_TOOL_NAMES = frozenset(item.name for item in OUTPUT_TOOLS)
_BY_TYPE = {item.output_type: item for item in OUTPUT_TOOLS}


def output_tool(output_type: type[BaseModel]) -> OutputTool:
    return _BY_TYPE[output_type]
