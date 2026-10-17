from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, create_model

from shared.contracts.memory_output import MemoryConsolidationOutput, MemoryExtractionOutput
from shared.contracts.response_output import ParticipationDecision, ResponsePlan
from shared.contracts.vision_output import ImageDescription, StickerDecision


class GroupRepeatDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeat: bool
    reason: str


def _decode_tool_result(value: object) -> object:
    """Normalize JSON-encoded tool arguments from model gateways before validation."""
    return json.loads(value) if isinstance(value, str) else value


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
            result=(Annotated[output_type, BeforeValidator(_decode_tool_result)], ...),
        )
        return cls(name, description, output_type, arguments)

    def model_tool(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.arguments_type.model_json_schema(),
        }


OUTPUT_TOOLS = (
    OutputTool.define("submit_response_plan", "Submit the reply, emotion, and action plan for this turn.", ResponsePlan),
    OutputTool.define("submit_participation_decision", "Submit the group participation decision and a short reason.", ParticipationDecision),
    OutputTool.define("submit_repeat_decision", "Submit the group repeat decision and a short reason.", GroupRepeatDecision),
    OutputTool.define("submit_image_description", "Submit the image type, visible content, and sticker classification.", ImageDescription),
    OutputTool.define("submit_sticker_decision", "Submit the candidate image type and sticker suitability.", StickerDecision),
    OutputTool.define("submit_memory_extraction", "Submit an episode summary and source-backed memory atoms.", MemoryExtractionOutput),
    OutputTool.define("submit_memory_document", "Submit the consolidated long-term knowledge document.", MemoryConsolidationOutput),
)
OUTPUT_TOOL_NAMES = frozenset(item.name for item in OUTPUT_TOOLS)
_BY_TYPE = {item.output_type: item for item in OUTPUT_TOOLS}


def output_tool(output_type: type[BaseModel]) -> OutputTool:
    return _BY_TYPE[output_type]
