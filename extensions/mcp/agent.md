# MCP 运行边界


现有入口为 `python -m extensions.mcp.mcp_server`。模块级 mcp 是统一服务实例，mcp_server.yaml 定义 stateless streamable HTTP 运行参数。

## 工具与资源结果

- 天气、音乐、网络搜索采用同一部署，工具包具有内聚的 schema、处理函数和配置。
- *_tool.py 定义 MCP schema 与处理函数，*_tool.yaml 定义名称、描述、参数边界、客户端参数及用户消息。
- QWeatherClient 提供和风天气结果，WebSearchClient 提供搜索结果，音乐工具提供控制指令接收与记录。
- HTTP client 的拥有者为 lifespan，工具从 MCPResources 取得对应资源。
- 每 AI 的工具目录与授权归 extension-host，MCP 提供原子工具能力。
- structured-output 提供七类模型结果契约，详见 [结果文档](../../docs/persona-memory-and-mcp-output.md)。

mcp_server.yaml 包含服务名、版本、transport、host、port、JSON response 和 stateless。工具 YAML 包含 schema、文本边界、超时与结果上限。真实凭据归连接环境，工具结果及诊断使用业务数据和脱敏资料。
