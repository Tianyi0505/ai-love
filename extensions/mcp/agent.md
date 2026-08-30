### Agent System

**MCP Server** (`extensions/mcp/mcp_server.py`):

- 进程入口是 `python -m extensions.mcp.mcp_server`；模块级 `mcp` 是唯一 MCP 服务实例，按 `mcp_server.yaml` 以 stateless streamable HTTP 运行。
- `lifespan()` 创建并关闭天气和网络搜索 HTTP client，通过 `MCPResources` 注入工具处理器。需要外部资源的工具应从 lifespan context 取依赖，不应创建进程级孤立 client。
- 天气、音乐和网络搜索都注册到同一部署。新增 MCP 能力应增加内聚子包并在这里注册，不新增同类部署单元。

**Tool Registration** (`extensions/mcp/weather/`, `extensions/mcp/music/`, `extensions/mcp/web_search/`):

- 每个工具由 `*_tool.py` 定义 MCP schema 与处理函数，`*_tool.yaml` 保存名称、描述、参数边界、客户端参数和用户消息。
- 天气通过 `QWeatherClient` 调用和风天气；网络搜索通过 `WebSearchClient` 获取并解析搜索结果；音乐工具当前只接收并记录控制指令，尚未连接真实播放器。
- MCP 只提供原子工具，不读取 Agent 定义，也不执行每 AI 授权。工具暴露与权限由 `extension-host` 统一处理。

**Runtime Configuration**:

- `mcp_server.yaml`：服务名、版本、transport、host、port、JSON response 与 stateless 模式。
- 各工具目录的 YAML：工具 schema、文本边界、超时与结果上限。
- 和风天气凭据来自连接环境配置；任何日志、错误或工具结果都不得泄露凭据。
