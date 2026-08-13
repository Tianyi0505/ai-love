# AI-Love

面向实时直播与社交平台的可插拔数字 AI 系统。AI 拥有持续身份、独立记忆、关系、作息、账号和工具能力；承认自己的数字身份，不伪装成人类身体。

## 当前架构

- `gateway`：QQ/B站/微信 Adapter 与账号级路由。非直播账号唯一绑定一个 AI。
- `ai-agent`：同一进程热加载多个 `AIRuntime`，不再一 AI 一容器。
- `orchestrator`：只处理直播阵容和舞台秩序，不参与 QQ/微信路由。
- `memory`：PostgreSQL + pgvector 中的关系、记忆、作用域、衰减和显式共享。
- `extension-host`：统一 Skill/MCP 工具协议、每 AI 绑定和硬权限边界。
- `mcp-weather`：标准 Streamable HTTP MCP 服务，提供和风天气实时天气与每日预报。
- `tts` / `avatar` / `stream` / `music`：语音、形象、推流和音乐能力。
- NATS：运行时事件总线。
- Nacos：`agent.catalog`、`agent.<ai_id>` 与服务配置的唯一来源。

## 代码包边界

```text
shared/
├── contracts/        # 维护跨服务事件、响应、社交消息和领域契约
├── infrastructure/   # 维护 NATS、Nacos、数据库连接与服务生命周期
└── vision/           # 维护 Gateway 与 AI Agent 共用的图像描述协议

services/
├── gateway/          # 处理渠道适配、QQ 空间协议和社交路由
├── ai_agent/         # 处理 Agent Loop、Prompt、大模型、消息理解与运行时
├── memory/           # 处理记忆策略、存储与关系
├── extension_host/   # 处理 Tool、Skill、MCP 协议、权限与 Provider
├── tts/              # 处理语音合成协议与引擎
└── ...               # 维护其余服务的私有实现
```

服务实现只能依赖自身包和 `shared`，不能直接导入其他微服务的内部代码。Docker 每个 target 也只复制 `shared` 和对应服务目录，以便在构建阶段暴露越界依赖。

AI 定义只从 Nacos 读取，完整结构示例位于 `deploy/nacos/`。运行时不扫描本地 Persona 目录，也不回退本地配置。

## 第一阶段约束

- 先接通现有单 QQ 账号，再接 B站。
- NapCat 登录态必须保留，部署不得重启或重建 NapCat。
- QQ 白名单沿用现有 Nacos 配置；私聊 24 小时被动回复，主动联系只在 AI 工作作息内。
- QQ 空间遍历全部好友，并按该 AI 与每个人的多维关系分别判断点赞和评论。
- 禁止工具删除消息、修改账号资料、读取或导出凭据。

## 配置

```text
agent.catalog             # 声明 active_ai_ids
agent.<ai_id>             # 配置身份、人格、Prompt、关系、作息、模型与工具
service.<service-name>    # 配置服务与 Adapter 参数
director.<session_id>     # 配置直播场次
ailove.config             # 配置全局运行参数与 QQ 白名单
```

新增 AI：发布一个新的 `agent.<ai_id>`，把 ID 加入 `agent.catalog`，并在账号绑定表中建立显式绑定。无需新增容器或复制记忆实现。

## 本地启动

```bash
docker compose -f deploy/docker-compose.yml up -d
```

生产部署不能通过初始化脚本覆盖服务器现有白名单，也不能重启或重建 NapCat。

技术栈：Python 3.11、PostgreSQL/pgvector、NATS、Nacos、Docker Compose、NapCat、OBS、Live2D、GPT-SoVITS。
