import inspect
from copy import deepcopy

from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import TextBlock, ToolCallBlock
from agentscope.model import ChatModelBase, ChatResponse, ChatUsage, FinishedReason

from shared.structured_output_tools import output_tool


class ValidatingOutputClient:
    """Unit substitute for the authorized MCP submission, covered by HTTP integration tests."""

    async def submit(self, output_type, arguments, context=None):
        return output_tool(output_type).arguments_type.model_validate(arguments).result


def tool_call(output, usage_metadata=None):
    usage = usage_metadata or {"input_tokens": 1, "output_tokens": 1}
    return ChatResponse(
        content=[ToolCallBlock(id="result-call", name="GenerateStructuredOutput", input=output.model_dump_json())],
        is_last=True, finished_reason=FinishedReason.COMPLETED,
        usage=ChatUsage(input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"], time=0),
    )


class ScriptedModel(ChatModelBase):
    def __init__(self, responses=(), callback=None):
        super().__init__(OpenAICredential(api_key="test"), "scripted", self.Parameters(), stream=False, max_retries=0)
        self.formatter = OpenAIChatFormatter()
        self.responses = list(responses)
        self.callback = callback
        self.requests = []
        self.bindings = []

    async def _call_api(self, model_name, messages, tools=None, tool_choice=None, **kwargs):
        self.requests.append(deepcopy(messages))
        self.bindings.append((tools, tool_choice))
        result = self.callback(messages, tools) if self.callback else self.responses.pop(0)
        return await result if inspect.isawaitable(result) else result


class ResultModel(ScriptedModel):
    def __init__(self, call):
        async def respond(messages, tools):
            result = await call(messages)
            if isinstance(result.get("parsing_error"), Exception):
                return ChatResponse(content=[TextBlock(text="invalid result")], is_last=True)
            return tool_call(result["parsed"])
        super().__init__(callback=respond)
