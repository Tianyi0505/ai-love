# 人设记忆与 MCP 结构化结果

运行时提示词以身份、事实归属、适用条件和结果要求表达规则。正式人物配置决定身份与关系设定，配置留白保持原有语义。群聊、主动联系、视觉、工具和记忆使用一致的表达标准。

## 模型结果契约

| 功能 | structured-output MCP 工具 |
| --- | --- |
| 回复、情绪、动作 | submit_response_plan |
| 群聊参与 | submit_participation_decision |
| 群聊复读 | submit_repeat_decision |
| 图片理解 | submit_image_description |
| 表情适用性 | submit_sticker_decision |
| 记忆提取 | submit_memory_extraction |
| 记忆文档 | submit_memory_document |

结果工具的 `result` 参数与 `structuredContent` 使用同一套共享 Pydantic 契约。模型完成凭证为对应 MCP 工具的合法结果。回复字段为 `speech`、`emotion`、`actions`，静默结果使用合法空 speech/actions。任务上下文装配对应结果工具，工具授权来自 AI 的 extensions 定义。

MCPOutputClient、NATS `tool.execute`、Extension Host 和 MCP HTTP 构成可信调用边界。参数支持对象表示与 JSON 字符串编码表示，类型校验保证最终结果符合契约。

## 身份与记忆结果

提取及文档整理具有正式人物配置的 system message。聊天资料包含 role、message_id 和人物归属，每条原子记忆具有片段内具体来源 ID；自我记忆具有双方互动来源，语义判定依据人设与证据。

核心身份由正式配置投影，成长章节具有来源及人格依据。数据库沿用来源字段，业务契约归 `shared/contracts`。原文、诊断快照和修订资料保存在私有部署目录。

`SelfMemoryRepair` 的事务结果包含自我文档更新和快照内历史条目的处理标记，保留原子内容、ID、人物记忆及关系数据。修复计划绑定原文版本、摘要、完整条目集合和内容摘要，修订稿身份与当前配置一致。应用条件为当前计划、明确写入授权以及记忆插件静止窗口。

核验入口：

```powershell
python -m memory.self_memory_repair --plan /private/repair-plan.json
```

事务应用入口为同一命令的 `--apply` 模式。共享配置的字段契约为 `extra=forbid`，服务与 identity_section 配置处于匹配版本。部署结果保留真实连接、密钥引用、个性化设置和 NapCat 实例。

## 本地验收结果

| 验收项 | 结果或范围 |
| --- | --- |
| 回归 | 217 passed、1 skipped |
| 静态检查 | Ruff 通过，52 个提示词模板语法有效 |
| 基础设施 | 专用本机 PostgreSQL 与 NATS 容器 |
| 记忆 | 活动提取、聚合、来源范围、固定身份及持久事务 |
| 修复计划 | 只读核验、计划时效与历史队列状态 |
| 工具协议 | 真实 NATS RPC、MCP HTTP 与七类结果 Schema |
| Agent | 业务工具与最终结果记录 |
| 生命周期与授权 | 插件状态、AI 授权、参数校验 |
| Agnes | HTTP 请求形状 |

LLM 回归采用可控响应，证据覆盖协议、来源约束和持久化行为。线上语义质量采用实际模型观察结果。

## 2026-09-30 交付结果

- 应用代码为 `1d54f85`，8 个应用镜像标签为 `persona-mcp-1d54f85-20260930`。
- 8 个服务的 16 项合并配置摘要一致，包含 52 个运行提示词；生产连接与 Secret 保留原值。
- 自我文档由版本 45 更新为 46，共 449 字；500 条历史自我记忆保留原文并具有已处理标记。
- 23 项真实 NATS/MCP 回归通过，覆盖两类参数表示、Agent 链路与参数范围。
- 发布验收包含七类 MCP 结果、真实模型直接回复、Agent 回复、记忆提取、管理登录及 structured-output 状态管理。
- 7 个宿主、18 个插件 active，8 个应用服务 Ready，公网页面 HTTP 200。
- NapCat 原实例的启动时间为 `2026-08-15T10:39:25Z`。
- 本地、core、app 的历史镜像回收数分别为 16、10、14；备份归私有部署目录。

## 2026-09-30 core 部署结果

gateway、ai-agent、director、extension-host、mcp、live-edge 的 Deployment 选择器固定为 `ailove-core`（106.55.16.95）。app 与 edge 的调度状态为 cordon。

六个服务使用集群 NATS 与 `ClusterFirstWithHostNet`，Agent 使用集群 Redis。NapCat 配置端口为 3000/3001，语音客户端端口为 9881；镜像标签为 `persona-mcp-1d54f85-20260930`。配置与 Deployment 备份位于 `deploy/private/core-migration-20260930`。

验收时 10 个 Pod 全部 Running/Ready、重启计数为 0；7 个宿主和 18 个插件 active。真实模型直接回复、Agent 回复、记忆提取及七类 MCP 往返成功，网关的 NapCat WebSocket 已连接。自我文档版本为 47，管理接口校验通过。

core 可用内存约 845 MB，Agent 实测约 283 MiB。共享数据库、NATS、Redis、core 数据及 NapCat 实例保留。当前验收证据的资源范围为 core；app、edge 的文件与归档核验以节点可访问及旧进程静止为条件。
