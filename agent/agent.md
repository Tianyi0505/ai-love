# Agent 与 Memory 运行边界


`ai-agent` 同进程托管多个 `AIRuntime` 和共享 `MemoryModule`。现有服务入口为 `python -m agent.ai_agent_service`，统一插件入口见 [插件运行时](../docs/plugin-runtime.md)。

## 身份与回合结果

- 每个 Runtime 对应一个稳定 `ai_id`，事件归属来自 Gateway 或 Director 的可信路由。
- AgentDefinitionStore 的人物定义由 agent.default 与 agent.<ai_id> 合并，catalog 和定义变化对应最新运行时目录。
- AgentSupervisor 是 Runtime 目录、热更新及分发并发的拥有者；fingerprint 相同的实例保持连续。
- 每个 Runtime 提供 Persona、Prompt、ChatAgent、Vision、Memory、Sticker、TTS、工具与社交策略。
- TurnCoordinator 保证同会话状态有序，各会话具有独立并发范围。
- 回复出口为 social.send.request，真实回合的记忆凭证为 memory.activity。
- 后台资源由 spawn() 登记，实例停止结果包含在途工作归零与 HTTP client 关闭。
- 主动联系满足工作时段、静默窗口、冷却及持久联系额度，话题依据长期记忆。

## Memory 结果

MemoryModule 的配置、总线、调度器、定义存储与数据库来自同一宿主。NATS RPC 提供记忆、关系与表情契约，JetStream durable consumer 持久接收活动。静默 Episode、Atom 和 person/self 文档使用 KV claim 与 PostgreSQL 来源。

停止完成状态涵盖 Agent 在途工作、Memory 订阅和共享基础资源。

## 配置归属

service.ai-agent 对应实例与轮询周期；agent.default 对应共享能力；agent.<ai_id> 对应个性化覆盖；ailove.config 对应模型、社交、记忆、超时及观测。账号绑定和启用状态来自 PostgreSQL。
