from __future__ import annotations

from mcp.types import ToolAnnotations

from shared.structured_output_tools import OUTPUT_TOOLS, OutputTool


def _handler(spec: OutputTool):
    async def submit(result):
        return spec.output_type.model_validate(result)

    submit.__annotations__ = {"result": spec.output_type, "return": spec.output_type}
    return submit


def register_structured_output(mcp) -> None:
    for spec in OUTPUT_TOOLS:
        mcp.tool(
            name=spec.name,
            description=spec.description,
            structured_output=True,
            annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
        )(_handler(spec))
