# AgentScope Runtime

AI-Love uses AgentScope for chat execution and structured tool output.

## Execution model

- ChatAgent sends a system prompt and a user prompt for each turn.
- FailoverChatAgent selects the configured multimodal model group and the text-model fallback.
- StructuredOutput validates each model result against its Pydantic contract.
- PromptAssembler builds the persona, context, scene, and output protocol.
- ToolExecutionContext carries trusted identity and conversation scope.

## Result contracts

The runtime produces typed response plans, group participation decisions, repeat decisions, image descriptions, sticker decisions, and memory output. The MCP structured-output tools validate these results before the application uses them.

## Context

The prompt includes the current user input, recent conversation, relevant memory, relationship context, entity context, and scene rules.
