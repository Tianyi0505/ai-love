# LangChain 能力设计结果

本文描述 LangChain 适配的目标产物和验收条件。

## 依赖与模型

运行依赖包含固定版本的 `langchain`、`langchain-deepseek`、`langchain-openai`、`langchain-anthropic` 和满足 LangGraph 约束的 `websockets`。`requirements.txt` 表达直接运行依赖。

模型工厂按 Agent 模型 ID 解析 `llm.models` 的 provider、模型名、地址和密钥环境变量，提供 DeepSeek、Anthropic、OpenAI chat model。每个实例包含 API key、base URL、输出预算、请求超时和有限重试配置。图片模型具有 OpenAI-compatible 入口与共享异步 HTTP client。

## 结果契约

| 能力 | 目标结果 |
| --- | --- |
| 结构化输出 | with_structured_output(..., include_raw=True) 返回已解析 Pydantic 对象与可定位解析结果 |
| 工具回复 | create_agent 与 ToolStrategy(ResponsePlan) 返回合法回复计划 |
| 调用预算 | ModelCallLimitMiddleware 限定每轮模型调用数 |
| 工具重试 | ToolRetryMiddleware 应用配置预算 |
| 普通回复与参与 | 对应输出类型的结构化对象 |
| 业务校验 | ResponseOutputPolicy 确认回复适用范围 |
| 扩展工具 | StructuredTool 使用 JSON Schema args_schema |
| 可信上下文 | ToolRuntime[ToolExecutionContext] 提供运行时身份与授权 |
| 工具请求 | arguments 承载模型参数，execution_context 承载可信身份 |
| 图片描述 | bytes/media type 与多模态消息对应 ImageDescription，并符合 VisionOutputPolicy |
| 记忆生成 | MemoryExtractionOutput、MemoryConsolidationOutput 满足结构化契约与调用预算 |

模型缓存键包含 `ai_id`、定义指纹和输出类型。视觉 HTTP client 的资源归属为 AIRuntime 生命周期。

## 可观测结果

模型 span 包含 provider、model、token 用量以及配置允许的请求资料；工具 span 沿现有 NATS 链路关联。ai-agent 的模型连接参数由部署环境提供。

验收覆盖模型目录、provider 路由、回复、参与、图片和记忆输出、调用预算、重试预算、参数与可信上下文各自归属。
