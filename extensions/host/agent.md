# 工具宿主运行边界


现有入口为 `python -m extensions.host.extension_host_service`，公开主题为 tool.list.request 和 tool.execute.request。工具目录与授权绑定对应启用人物定义及当前 MCP 服务目录。

## 授权结果

Extension Host 是 Agent 工具执行的统一可信授权边界。ToolGateway 按 (ai_id, tool_id) 的 ToolGrant 确定可见性、执行资格与 permission level。

ToolExecutionContext 的 ai_id 以已验证请求顶层身份为准，账号、平台和会话范围来自可信上下文。provider 的职责为发现与调用，ToolResult 和 RPC 错误码表达实际结果。

MCPToolProvider 提供配置地址的 streamable HTTP；GroundingToolProvider 提供 Gateway 实体解析和群聊历史 NATS 契约。

service.extension-host 包含 binding_poll_interval_sec、grounding_timeout_sec 和 mcp_url；工具启用、权限及 provider 配置来自 agent.default / agent.<ai_id> 的 extensions 定义。
