### Agent System

**AI Agent Service** (`agent/ai_agent_service.py`):

- 进程入口是 `python -m agent.ai_agent_service`；`AIAgentService` 继承 `BaseService`，以 `ai-agent` 使用 Kubernetes 挂载配置，并在同一进程启动共享 Memory Module，再订阅 `social.chat.>`、`agent.live.>` 和相关 RPC。
- 启动时从 PostgreSQL 读取启用的 AI，再通过 `AgentDefinitionStore` 合并 `agent.default` 与 `agent.<ai_id>`。`agent.catalog`、默认定义或个体定义变化时，服务会重新 reconcile 运行时。
- 一个进程托管多个 AI。事件必须携带已经由 Gateway 或 Director 确定的 `ai_id`；服务不根据账号或直播事件自行猜测归属。

**Agent Supervisor** (`agent/agent_supervisor.py`):

- `AgentSupervisor` 以 `ai_id` 管理 `AIRuntime`。定义 fingerprint 不变时保留现有实例；定义变化时先启动替代实例，再 drain 并停止旧实例；移除的 AI 同样先 drain。
- 分发入口只接受已激活的 AI。热更新、停止和分发的并发规则集中在 Supervisor，不应在消息处理器里维护第二份运行时目录。

**AI Runtime** (`agent/ai_runtime.py`):

- 每个 `AIRuntime` 只服务一个 AI，组装 Persona、Prompt、ChatAgent、Vision、Memory、Sticker、TTS、工具集、会话状态、群聊参与策略和主动私聊调度。
- Agent 定义只保存对话模型 ID，`create_chat_model()` 从全局 `llm.models` 解析 provider、模型名、地址和密钥环境变量后创建模型；视觉模型由 `create_openai_compatible_chat_model()` 创建。扩展工具通过 `tool.list.request` 动态加载，TTS 通过 `ai_love.tts` entry point 加载。
- 同一会话使用 `TurnCoordinator` 串行演进，不同会话可并发。社交回合完成后发布 `memory.activity`；回复只能通过 `social.send.request` 返回 Gateway。
- Runtime 替换前必须等待 `_in_flight` 归零；新增后台任务必须经 `spawn()` 登记，以便停止时统一取消并关闭 HTTP client。
- 主动私聊按工作时段周期检查关系候选人，满足静默期后基于长期记忆生成具体话题；发送后必须等对方回复并遵守冷却时间。主动消息同样只经 `social.send.request` 发往 Gateway。

**Memory Module** (`memory/memory_module.py`, `memory/memory_pipeline.py`):

- `MemoryModule` 不是独立服务；它复用 `AIAgentService` 的 Kubernetes 挂载配置、NATS、调度器、Agent 定义存储和 PostgreSQL 连接，由 Agent 服务统一启动和停止。
- 记忆、关系和表情仍通过既有 NATS RPC subject 提供，`memory.activity` 仍由 JetStream durable consumer 处理。保留该契约是为了隔离 Runtime 与持久化实现，不代表独立部署边界。
- 联系人静默后提取 Episode 与原子记忆，达到阈值后再合并 person/self Markdown；KV claim、PostgreSQL 事实来源、输出策略和容量淘汰不因部署合并而改变。
- 停止顺序是先 drain Agent Runtime，再取消 Memory RPC/durable subscriptions，最后关闭 Redis、PostgreSQL 与共享 Bus。

**Runtime Configuration**:

- `service.ai-agent`：服务实例和目录轮询周期。
- `agent.default`：共享 Prompt、行为、模型、工具、关系与声音配置。
- `agent.<ai_id>`：身份、人格、模型 profile、形象与个体覆盖；列表字段按整体覆盖处理。
- `ailove.config`：LLM、视觉、TTS、记忆、社交、超时和可观测性参数；记忆模块没有独立服务配置。账号绑定与启用状态来自 PostgreSQL。
