# AgentScope 运行时

模型调用统一使用 `agentscope==2.0.9`，包括对话、群聊参与与复读、视觉、表情判断、记忆提取和文档整理。供应商工厂返回 SDK 的 `OpenAIChatModel`、`DeepSeekChatModel` 或 `AnthropicChatModel`；模型目录、凭据环境变量、超时与有限重试由既有配置提供。Agnes 使用 OpenAI 兼容接口及 `max_tokens` 参数。

`StructuredOutput.generate()` 为每次调用建立原生 `Agent`，通过 `reply(structured_schema=...)` 获得经过 Pydantic 校验的结果。SDK 的 `GenerateStructuredOutput` 工具负责生成、校验和错误反馈，ReActConfig 约束推理迭代；最后一次迭代用于完成结构化结果，合计不超过配置的请求次数。供应商网络重试由 SDK 模型管理。取消会向业务调用者传播。

每个回合使用独立 `AgentState` 和 `Toolkit`，并发会话不共享短期状态。已有上下文装配器仍提供人物、来源与历史资料，长期记忆仍由 MemoryModule 维护。会话业务排序、账号路由和发送去重由现有入口管理。

工具目录通过 Extension Host 动态加载为 SDK `FunctionTool`。每轮获取最新目录，执行时仍由 Extension Host 校验当前授权。可信 `ToolExecutionContext` 放在 AgentState 中并由 SDK 注入，模型参数与可信身份分开传输；工具 Schema 不暴露可信上下文。业务工具按顺序执行，失败结果交还 SDK 的 ReAct 循环处理，受同一请求预算约束。

SDK 完成结构化输出后，结果经 `MCPOutputClient`、NATS、Extension Host 和 MCP HTTP 进行授权与业务契约确认。七种 `submit_*` 仍是内部提交接口，模型只看见原生 `GenerateStructuredOutput`。最终回复仍通过 ResponseCommand 发送，结果字段保持 `speech`、`emotion` 和 `actions`。

AgentScope 2.0.9 的依赖要求为 MCP 1.x，项目固定使用 `mcp==1.30.0` 的 FastMCP、ClientSession 与 streamable HTTP。工具热更新、结果 Schema、插件生命周期和权限过滤均通过真实 MCP HTTP 与 NATS 回归验证。

用量来自 SDK 最终消息汇总的 token 数据。原有 OpenTelemetry 内容开关继续控制文本和图片的记录，SDK 不启用额外的内容导出。
