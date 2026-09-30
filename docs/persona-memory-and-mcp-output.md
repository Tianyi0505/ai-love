# 人设记忆与 MCP 结构化结果

## 结果

运行时提示词使用身份、事实归属、适用条件和结果要求表达规则。正式人物配置决定身份与关系设定，配置留白保持留白。群聊、主动联系、视觉、工具和记忆提示词遵循同一表达方式。

七类模型结果均通过 `structured-output` 插件的 MCP 工具提交：

| 功能 | MCP 工具 |
| --- | --- |
| 回复、情绪、动作 | `submit_response_plan` |
| 群聊参与 | `submit_participation_decision` |
| 群聊复读 | `submit_repeat_decision` |
| 图片理解 | `submit_image_description` |
| 表情适用性 | `submit_sticker_decision` |
| 记忆提取 | `submit_memory_extraction` |
| 记忆文档整理 | `submit_memory_document` |

模型通过 function calling 填写 `result` 参数，MCP 服务按照 Pydantic 类型校验并返回 `structuredContent`。服务端输出 Schema 和客户端参数 Schema 使用同一套共享契约。提示词描述结果含义，工具 Schema 定义字段结构。

调用链：业务入口 → 模型工具调用 → MCPOutputClient → NATS tool.execute → Extension Host 授权 → MCP HTTP → structured-output 插件 → typed result → 业务规则校验。

对话 Agent 使用普通业务工具获取资料，独立调用 `submit_response_plan` 完成本轮。参与、复读、视觉和记忆任务绑定对应结果工具。静默回复仍使用合法的空 speech/actions。正文 JSON 和普通文本均不能替代 MCP 完成记录。回复契约只有 speech、emotion、actions，旧提示词中的 tool_calls、memory_candidates 已移除。

结构化结果工具在普通业务工具目录中隐藏，各任务装配自己的结果工具；服务端仍按 AI 的 extensions 配置授权。停用插件会使结果调用失败，恢复后继续使用同一通路。模型解析和结果提交遵循现有重试上限；记忆任务失败回到调度重试，表情和复读失败沿用文字回复/旁听逻辑。

MCP 保证协议结构和服务端类型检查；模型内容真实性与业务适用性仍由来源验证、正式人设和业务规则共同保证。协议参考：[MCP Tools：Structured Content / Output Schema](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。

## 人设污染的生产证据与修复

2026-09-28 的只读快照显示：线上自我认知文档版本为 44，包含 500 条自我记忆记录。涉及免费服务器、住客和“没有主人”的条目可沿 source_message_ids 追到 AI 自己的历史发言。正式人设只定义洛雨的持续数字身份、性格和表达方式，没有这些运行资料或归属声明。

真实路径为：已存聊天消息 → 记忆活动队列 → MemoryPipeline 提取 → 原子记忆 → 聚合队列 → 自我认知 Markdown → 对话上下文/管理页面。旧实现只给记忆模型任务文本，每条原子记忆关联整个片段的消息，核心身份可被生成内容覆盖。

修复后：

- 提取与整理均携带正式人物配置的 system message。
- 聊天数据明确 role、message_id 和人物归属；每条记忆提供具体来源 ID。
- 来源 ID 必须属于实际片段；自我记忆至少具有双方互动来源。这个条件能过滤单方自述，语义真实性仍需人设与证据判断。
- 聚合前后的核心身份由正式人物配置投影生成；其他成长章节继续按来源和人设标准整理。
- 数据库沿用现有来源字段，业务契约集中在 shared/contracts，兼容旧导入路径。

历史数据保持独立修复：原文与诊断快照位于忽略提交的 deploy/private 目录。修订草稿以正式配置为身份基准，保留可追溯到实际发言的道歉、称呼纠正和词语解释三项数字互动经历。仅替换长信不足以处理仍在聚合队列中的旧原子记忆。快照中 consolidated_at 为空的记录不能直接视为当前队列任务。

`SelfMemoryRepair` 将文档更新与快照内旧自我条目的已处理标记放在同一事务中，原子记忆内容和 ID 完整保留。人物记忆与关系数据保持原值。聚合入口按照 owner 及 consolidated_at 读取待处理条目，旧队列重放会自然完成，新条目继续参与聚合。

修复计划同时绑定原文版本、原文摘要、完整自我条目集合及条目内容摘要。任何变化都会要求使用最新快照复核；修订稿核心身份须与当前配置一致。执行前暂停并 drain 记忆插件，以保证检查与应用窗口内的写入状态稳定。

```powershell
# 默认只读核对；配置和数据库连接来自当前部署环境
python -m memory.self_memory_repair --plan /private/repair-plan.json

# 明确批准线上更新后，在记忆插件已暂停并 drain 的窗口应用
python -m memory.self_memory_repair --plan /private/repair-plan.json --apply
```

## 发布顺序

代码已合并 main，2026-09-30 发布记录与后续节点故障见下文。

1. 备份线上 ConfigMap、人物配置、自我文档、相关原子记忆与当前记忆队列，并记录文档版本。
2. 暂停并 drain 记忆/对话插件，完成旧任务与新配置的版本切换。
3. 发布支持新增 identity_section 字段的共享配置读取代码；发布 MCP 的 structured-output 插件并验证七个工具的输入/输出 Schema。
4. 将新提示词、身份正向表述、identity_section 与七个工具授权合并到实际 Kubernetes 配置，保留真实连接参数、密钥引用和个性化设置。发布包含新调用链的 ai-agent。
5. 对照批准的修订稿，通过 SelfMemoryRepair 事务更新自我认知并标记历史自我条目已处理，备份保留用于回退。
6. 恢复插件，通过只读接口核对文档、插件状态及 MCP 结果日志；新部署稳定后再按部署约定清理旧项目镜像。

共享配置采用 extra=forbid，旧服务无法读取新增 identity_section。镜像与配置切换需要统一安排；运行中的 memory/agent 应在切换窗口保持暂停。NapCat 沿用当前容器。

## 验证范围

测试覆盖 PostgreSQL 的真实活动提取/聚合入口、来源越界重试、固定核心身份、修订稿默认只读与事务应用、过期计划拒绝、旧队列重放、真实 NATS RPC 与 MCP HTTP、七类结果 Schema、Agent 业务工具后提交结果、插件停用/恢复、未授权 AI、无效 MCP 参数，以及 Agnes HTTP 请求形状。

LLM 在本地测试中由可控响应替代，验证的是协议、来源约束和持久化行为；线上模型的语义质量仍需要部署后的实际观察。

本地验收结果：217 passed、1 skipped（显式启用的私聊负载测试）；Ruff 检查通过，52 个提示词模板语法有效。PostgreSQL 与 NATS 使用专用本机测试容器。

## 2026-09-30 发布记录

- 运行代码：`1d54f85`，8 个应用镜像统一为 `persona-mcp-1d54f85-20260930`。main 已完成本地快进合并。
- 8 个服务的 16 项合并配置摘要一致，包含 52 个运行提示词。生产连接配置与 Secret 保持原值。
- 自我长信由版本 45 事务更新为 46，共 449 字；500 条旧自我记忆保留原文并标记已处理。修订稿还保留了一项经原始发言核实的群史时间线写作提议。
- 真实模型返回的工具参数中出现字符串编码的 result；参数边界增加解码，随后继续执行类型校验和 MCP 调用。23 项真实 NATS/MCP 回归测试通过，包括两类参数表示、Agent 调用链及无效值拒绝。
- 发布时验收通过：7 类 MCP 结果往返、真实模型直接回复/Agent 回复/记忆提取、管理页面登录、structured-output 停用与启用、7 个宿主和 18 个 active 插件；8 个应用服务 Ready，公网页面 HTTP 200。
- NapCat 容器保持原实例，启动时间仍为 2026-08-15T10:39:25Z。
- 已清理本地 16 个、core 10 个、app 14 个旧项目镜像。已删除本地 6 份旧镜像归档、core 的旧发布归档及旧临时传输包。配置与记忆备份保留在忽略提交的 deploy/private 中。

### 后续复查的阻塞

2026-09-30 11:38:33（北京时间），app 节点 iziahxpba1nr6oz 状态转为 Unknown，最后心跳为 11:36:55。稍后复查时，6 个 app 服务的旧 Pod 处于 Terminating，新 Pod 因节点不可达而 Pending。从本地和 core 发起 SSH 均在 banner 握手阶段超时。core、管理页面、NATS、Redis 和 gptsovits 仍正常。发布成功时的验收记录不代表故障后的当前可用状态。

需要通过云控制台恢复 app 节点，再检查插件、业务调用及余下归档清理。app 的旧发布归档和旧临时传输包尚未删除；长期离线的 edge 节点也无法核验或清理。MCP 日志另有 localhost:4317 链路追踪收集器连接失败，业务 MCP 验收通过；可观测性上报需要单独恢复。

## 2026-09-30 core 节点迁移

按用户要求，将 app 上的 gateway、ai-agent、director、extension-host、mcp、live-edge 迁移至在线的 ailove-core（106.55.16.95）。离线 app 与 edge 已 cordon。旧 app Pod 已从控制面移除，Deployment 选择器固定为 core；离线节点恢复后仍需核对旧进程已退出，避免重复消费。

6 个服务改用集群 NATS 地址与 ClusterFirstWithHostNet DNS，Agent 使用集群 Redis 地址。线上 ConfigMap 中 NapCat 地址改为 core 的 3000/3001 端口，语音客户端改为 9881。镜像继续使用 persona-mcp-1d54f85-20260930，无需重新构建。运行配置与迁移前 Deployment 备份位于 deploy/private/core-migration-20260930。

验收：10 个 Pod 全部 Running/Ready、零重启；7 个宿主和 18 个插件 active；真实模型直接回复、Agent 回复和记忆提取成功，七类 MCP 往返通过；网关日志确认 NapCat WebSocket 已连接。自我文档继续更新至版本 47，管理接口校验通过。迁移后节点可用内存约 845MB，Agent 实测约 283MiB。NapCat 容器及启动时间保持原值。

共享数据库、NATS、Redis 与 core 已有数据继续使用。离线 app 的本地文件和插件操作日志暂时无法读取；新宿主按插件清单重建默认启用状态，与上次验收的 18 个 active 插件一致。离线节点的文件恢复及旧镜像归档清理仍待节点可访问后处理。模型调用期间出现过一次上游超时，后续真实调用验收成功。
