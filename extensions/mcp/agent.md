# MCP Runtime

Start the MCP service with python -m extensions.mcp.mcp_server. One stateless streamable HTTP server exposes the MCP tools.

## Tool results

- Weather, music control, web search, and structured output share one deployment.
- Each tool package defines its schema, handler, client settings, and result form.
- The weather client returns weather data.
- The web-search client returns search results.
- The music tool records a control command.
- The extension host assigns each AI tool catalog and tool grant.
- Structured-output tools validate model results.

mcp_server.yaml defines the server name, transport, address, JSON responses, and stateless mode. Tool YAML files define input limits, timeouts, and result limits. Deployment resources provide service credentials.
