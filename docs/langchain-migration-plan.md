# LangChain 迁移改造清单

## 依赖

- 用 `langchain`、`langchain-deepseek`、`langchain-openai`、`langchain-anthropic` 替换 `pydantic-ai-slim`。
- 将 `requirements.txt` 恢复为项目直接运行依赖清单并固定已验证版本。
- 将 `websockets` 固定为与 LangGraph 依赖约束兼容的版本。

## 模型创建

- 新增 `shared/infrastructure/chat_model_factory.py`。
- 解析 `provider:model` 配置，并创建 DeepSeek、Anthropic 或 OpenAI chat model。
- 注入 API key、base URL、最大输出 token、请求超时和网络重试次数。
- 为图片理解提供 OpenAI-compatible 模型创建入口和共享异步 HTTP client。

## 结构化输出

- 新增 `shared/infrastructure/langchain_structured_output.py`。
- 使用 `with_structured_output(..., include_raw=True)` 生成 Pydantic 输出。
- 将解析错误转为可重试异常，并按请求次数与重试配置限制调用次数。
- 从结果中统一读取已解析对象并透传解析异常。

## ChatAgent

- 使用 LangChain v1 `create_agent` 和 `ToolStrategy(ResponsePlan)` 实现带工具的回复循环。
- 使用 `ModelCallLimitMiddleware` 限制每轮模型调用次数。
- 使用 `ToolRetryMiddleware` 应用工具重试配置。
- 使用 `with_structured_output` 实现无工具回复与参与决策。
- 在返回前执行 `ResponseOutputPolicy` 校验。

## 扩展工具

- 将 extension host 工具定义转换为 `StructuredTool`。
- 将工具 JSON Schema 写入 `args_schema`。
- 使用 `ToolRuntime[ToolExecutionContext]` 注入可信执行上下文。
- 将模型参数写入 `ToolExecuteRequest.arguments`，将可信上下文写入 `execution_context`。
- 在工具执行 span 内调用 `tool.execute.request`。

## 图片理解

- 将图片下载结果改为 bytes 与 media type 数据对象。
- 将图片编码为 data URL 并构造 LangChain 多模态消息。
- 使用 `with_structured_output(ImageDescription)` 解析并执行 `VisionOutputPolicy` 校验。
- 在 `AIRuntime.stop()` 中关闭视觉模型共享 HTTP client。

## 记忆生成

- 使用统一模型工厂创建记忆模型。
- 按 `ai_id`、定义指纹和输出类型缓存模型与 structured runnable。
- 对 `MemoryExtractionOutput` 和 `MemoryConsolidationOutput` 使用结构化输出与重试限制。

## 观测与部署配置

- 新增 LangChain 模型 span，记录 provider、model、token 用量和受开关控制的请求参数及内容。
- 新增工具调用 span，并沿现有 NATS 调用传播上下文。
- 向 ai-agent 和 memory 容器注入 DeepSeek API key 与 base URL。

## 验证

- 验证 DeepSeek、Anthropic 和 OpenAI-compatible 模型路由。
- 验证回复、参与决策、图片描述和记忆输出的结构化解析。
- 验证解析失败重试、模型调用上限和工具重试配置。
- 验证模型参数与可信工具上下文隔离。
- 验证旧 PydanticAI 代码引用与依赖全部移除。
