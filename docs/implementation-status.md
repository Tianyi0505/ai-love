# 当前目标与实施状态

更新日期：2026-10-21

## 当前目标

将 AI-Love 从旧 Python 微服务架构迁移为运行在 DeepSeek Harness（DSH）上的一体化 TypeScript 插件：

- DSH 负责 Agent 核心、模型、会话、工具、日志和整体运维。
- 业务功能作为插件运行，不重建 DSH 已提供的控制面。
- 插件划分按互不相关的业务功能进行；插件之间业务依赖为零。
- 任一业务插件缺失或故障都不能影响 DSH 核心功能。
- 仓库可以直接作为 DSH 插件导入。
- 每个群聊或私聊对应一个稳定的 DSH 会话。
- 指定项目目录中的 Markdown 文件既是 Agent 工作区，也是跨会话记忆存储；Agent 直接读取和更新这些文件。
- 新增实现统一使用 TypeScript，不使用 JavaScript。

## 当前架构

当前仓库只导出一个业务插件 `ai-love`，业务插件依赖图为单节点、零边。聊天通道通过薄 HTTP 入口提交消息；DSH 原生 Agent/Session 执行对话；Agent 直接使用 DSH 文件工具维护项目目录中的 Markdown。

```text
聊天平台
  -> AI-Love HTTP 入口
  -> DSH Agent / Session
  -> <项目目录>/.ai-love/memory/**/*.md
```

每个聊天使用 `platform + accountId + chatType + chatId` 的稳定摘要生成 DSH 会话 ID。任一项不同即为不同会话；同一组字段会恢复同一会话。

Markdown 记忆分为三层：

```text
<项目目录>/.ai-love/memory/
├── shared/README.md
├── identities/<identity>/MEMORY.md
└── conversations/<session-id>/MEMORY.md
```

- `shared`：允许跨所有身份和聊天共享的事实。
- `identities`：同一数字身份跨聊天共享的事实。
- `conversations`：仅属于单个群聊或私聊的事实。

## 已完成

- 已删除旧 Python 微服务、NATS、PostgreSQL、独立网关、Agent、记忆、语音、直播和运维控制面实现。
- 已将旧实现移出仓库并保留在 `D:\ai-love-legacy-backup-20261021`，其中 Git 已跟踪文件仍可从版本历史恢复。
- 已建立单一 TypeScript DSH 插件 `ai-love`，业务插件之间无相互依赖。
- 已实现稳定聊天到 DSH 会话的映射及同一会话内串行处理。
- 已实现指定目录内的共享、身份、会话三级 Markdown 记忆结构。
- 已把 Agent 工作目录和 DSH 启动目录统一到 `AILOVE_WORKSPACE_DIRECTORY`。
- 已实现 TypeScript HTTP 消息入口、Bearer Token、请求体上限和健康检查。
- 已提供本地启动脚本、DSH profile 模板、Dockerfile、Compose 配置和环境变量示例。
- 已重写根目录及运行时文档，使部署、导入、会话和记忆行为与当前实现一致。

## 验证结果

- `pnpm test`：类型检查和 5 项测试全部通过。
- 测试覆盖：单插件零业务依赖、聊天会话映射、Markdown 记忆、消息兼容输入、无 Agent 服务时的真实 Cordis 加载与卸载。
- 全新 DSH_HOME 中执行 `dsh plugin --profile web add D:\ai-love` 成功。
- DSH 配置合成后只出现一个 `ai-love` 业务插件。
- 从干净临时仓库直接导入成功；仓库不依赖预先安装自身的前置依赖。
- 本地 DSH 启动成功，`/healthz` 返回健康，指定目录内 Markdown 记忆成功创建。
- Docker 镜像完整构建成功。
- 容器内 DSH 成功加载插件、创建 Markdown 记忆，入口健康检查通过。
- Compose 配置校验和 Dockerfile 静态检查通过。
- 活跃源码中未发现 Python、JavaScript、NATS 或旧微服务运行时残留。

## 已知边界

- 按用户要求，仓库交付形态是“直接导入仓库路径”。由于 Node.js 22 不支持在 `node_modules` 中直接剥离 TypeScript 类型，把 TypeScript 源码打成 npm 包后再安装并不属于当前交付路径。
- 真实模型对话需要有效的 `DEEPSEEK_API_KEY`；自动验证使用占位 Key 覆盖启动、插件加载、HTTP 入口和 Markdown 文件边界，不调用外部模型。
- 公共网络绑定必须自行配置 `AILOVE_INGRESS_TOKEN`，否则入口会拒绝启动。

## 后续可选事项

- 为具体聊天平台实现独立的通道适配插件；该插件可单独缺失，不影响 DSH 或其他业务插件。
- 根据真实消息量增加鉴权轮换、限流和可观测性。
- 在真实模型 Key 下执行端到端对话验收。
