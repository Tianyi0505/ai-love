# Extension Host Runtime

Start the host with python -m extensions.host.extension_host_service. The public subjects are tool.list.request and tool.execute.request.

## Authorization results

The extension host is the trusted boundary for agent tool execution. ToolGateway uses each (ai_id, tool_id) grant to define tool visibility, execution authority, and permission level.

ToolExecutionContext carries a verified AI identity, account, platform, and conversation scope. Providers discover and invoke tools. ToolResult and RPC error codes describe the result.

MCPToolProvider serves configured streamable HTTP tools. GroundingToolProvider serves gateway entity and group-history contracts.

service.extension-host defines polling, grounding timeout, and MCP URL settings. Agent definitions provide the active tool grants and provider configuration.
