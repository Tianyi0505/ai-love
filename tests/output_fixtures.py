from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from shared.structured_output_tools import output_tool


class ValidatingOutputClient:
    """Unit-test substitute; the HTTP MCP integration tests exercise the real client."""

    async def submit(self, output_type, arguments, context=None):
        return output_tool(output_type).arguments_type.model_validate(arguments).result


def tool_call(output, usage_metadata=None):
    return AIMessage(
        content="",
        tool_calls=[{
            "id": "result-call", "name": output_tool(type(output)).name,
            "args": {"result": output.model_dump(mode="json")},
        }],
        usage_metadata=usage_metadata,
    )


def tool_runnable(runnable):
    def convert(result):
        if isinstance(result.get("parsing_error"), Exception):
            return AIMessage(content="schema-invalid result")
        return tool_call(result["parsed"], result["raw"].usage_metadata)

    return runnable | RunnableLambda(convert)


def completed_output(output):
    return ToolMessage(
        content="完成", name=output_tool(type(output)).name, tool_call_id="result-call",
        artifact=output.model_dump(mode="json"),
    )
