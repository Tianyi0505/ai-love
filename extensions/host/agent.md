### Agent System

**Extension Host Service** (`extensions/host/extension_host_service.py`):

- 进程入口是 `python -m extensions.host.extension_host_service`；`ExtensionHostService` 继承 `BaseService`，以 `extension-host` 使用 Kubernetes 挂载配置，并响应 `tool.list.request` 与 `tool.execute.request`。
- 服务启动和定时轮询时读取所有启用的 Agent 定义，发现统一 MCP 服务，并据此重建工具 provider、授权 binding 与 fingerprint。
- Extension Host 是 Agent 与具体工具之间唯一的授权边界。Agent 不能绕过它直接调用 MCP，MCP 也不负责理解 AI 身份或授权策略。

**Tool Gateway** (`extensions/host/tool_gateway.py`):

- `ToolGateway` 合并 Grounding 与 MCP provider 的定义，并按 `(ai_id, tool_id)` 的 `ToolGrant` 决定工具是否可见、是否可执行及其 permission level。
- 执行时始终以请求顶层的 `ai_id` 重建 `ToolExecutionContext`，忽略调用方 context 中可能伪造的 `ai_id`；这一授权不变量不可下放给 provider。
- provider 只实现工具发现和调用。业务错误经 `ToolResult` 返回，未授权或调用失败由服务边界转换为 RPC 错误。

**Providers** (`extensions/host/mcp_tool_provider.py`, `extensions/host/grounding_tool_provider.py`):

- `MCPToolProvider` 通过配置的 streamable HTTP 地址发现并调用统一 MCP 工具。
- `GroundingToolProvider` 通过 NATS 调用 Gateway 提供的实体解析和群聊历史能力，继续复用原始 `ToolExecutionContext` 的账号、平台和会话范围。

**Runtime Configuration** (`service.extension-host`):

- `binding_poll_interval_sec` 控制定义与绑定刷新周期。
- `grounding_timeout_sec` 控制 Gateway grounding RPC 超时。
- `mcp_url` 指向统一 MCP 服务；工具启用、permission 与 provider 配置来自 `agent.default` / `agent.<ai_id>` 的 extensions 定义。
