# AI-Love

面向实时直播与社交平台的数字 AI 系统。AI 拥有持续身份、独立记忆、关系、作息、账号和工具能力；承认自己的数字身份，不伪装成人类身体。

## 调用关系

```mermaid
flowchart LR
    G["Gateway<br/>平台接入"]
    A["Agent<br/>理解与决策"]

    LLM["LLM"]
    V["Vision"]
    ASR["ASR"]
    TTS["TTS"]

    M["Memory"]
    EH["Extension Host"]
    MCP["MCP"]

    G -->|"文字 / 图片 URL / 语音 URL"| A

    A -->|"模型生成"| LLM
    A -->|"图片理解"| V
    A -->|"语音识别"| ASR
    A -->|"记忆 / 关系 / 表情"| M
    A -->|"工具调用"| EH
    EH -->|"MCP 调用"| MCP
    A -->|"文本回复"| G
    A -->|"语音合成"| TTS
    TTS -->|"音频"| G
```

Gateway 只处理平台协议、账号路由和消息归一化。它把文字、图片 URL、语音 URL 交给 Agent，不负责图片理解、语音识别或回复决策。

## 代码包边界

```text
agent/                      # Agent 运行时：对话、图片理解、上下文与外部服务客户端
gptsovits/                  # 语音合成服务及 GPT-SoVITS、MIMO 引擎
gateway/                    # 平台接入、消息归一化、账号路由与 QQ 空间
memory/                     # 记忆、关系、表情与持久化
extensions/
├── host/                   # 工具发现、绑定、权限和调用网关
└── mcp/                    # 单一 MCP 进程
    ├── weather/            # 天气工具
    ├── music/              # 音乐控制工具
    └── web_search/         # 网络搜索工具
live/
├── director/               # 直播阵容和发言调度
├── avatar/                 # 形象与舞台事件模块
├── stream/                 # OBS 与推流控制模块
└── edge_service.py         # edge 侧统一进程入口
shared/
├── contracts/              # 跨进程消息契约；rpc/ 保留请求响应命名空间
├── *_settings.py           # 跨运行单元配置模型
├── *_repository.py         # 确实被多个运行单元复用的数据访问
└── nats_bus.py 等          # 共享运行时能力
```

顶层包对应可独立理解或运行的业务单元。包内默认使用扁平模块，文件名直接表达职责；只有跨多个模块的真实功能域才建立子包，例如 `contracts.rpc`、各 MCP 工具、直播组件和管理端功能。`shared` 只存放确实被多个运行单元共同使用的契约与实现，不接收单一服务的私有代码。

## 包与微服务

拆包不等于拆微服务。当前部署单元为：

- `gateway`：包含 `gateway` 包。
- `ai-agent`：包含 `agent` 包；一个进程可热加载多个 Agent Runtime。
- `gptsovits`：包含 `gptsovits` 包，通过 HTTP 和 NATS 提供合成能力；Agent 侧适配位于 `agent.gpt_sovits_provider`。
- `memory`：包含扁平的 `memory` 包。
- `extension-host`：包含 `extensions.host`。
- `mcp`：唯一 MCP 部署，同时加载天气、音乐和网络搜索能力，新增 MCP 能力不新增部署。
- `director`：承载直播阵容和发言调度。
- `live-edge`：合并承载 avatar 与 stream 两个 edge 侧直播模块。

音乐能力目前保持原实现范围：MCP 工具负责接收并记录控制指令，实际播放器适配器仍待接入。

NATS 是运行时事件总线。Nacos 是 `agent.catalog`、`agent.default`、`agent.<ai_id>`、服务配置和全局配置的来源。

## 长期记忆链路

消息处理阶段不调用记忆模型。Agent 在一个真实消息回合结束后只发布 `memory.activity`；Memory 服务用 JetStream 持久订阅活动事件，并在 JetStream KV 中保存每个 `ai_id + person_id` 的最新活动水位。

联系人进入静默期后，Memory 从 PostgreSQL 的真实 `messages` 调用链读取尚未处理的完整会话片段，一次生成 Episode 摘要和原子记忆。原子记忆先写入 `memory_atoms`，随后按联系人或 AI 自身进入 KV 聚合批次；达到 Episode 数、Atom 数、估算 token 数或最长等待时间任一阈值后，才调用一次合并模型更新 `memory_documents`。

```text
message → memory.activity → quiet episode → memory_atoms
        → pending batch → person/self consolidation → memory_documents
```

同一 owner 的提取与合并通过 KV revision 的 CAS claim 串行化，不同 owner 可以并行。`person` 和 `self` 使用独立阈值，`self` 的更新更保守。对话 Prompt 动态装配固定身份、自我 Markdown、联系人 Markdown、历史 Episode 摘要、近期原文和本轮消息。

## 配置

```text
agent.catalog             # 声明 active_ai_ids
agent.default             # 配置所有 AI 共用的 Prompt、关系、作息、模型与工具
agent.<ai_id>             # 只配置身份、人格、声音与形象等个性化覆盖
service.<service-name>    # 配置服务与平台 Adapter 参数
director.<session_id>     # 配置直播场次
ailove.config             # 配置全局运行参数与 QQ 白名单
```

新增 AI：发布精简的 `agent.<ai_id>` 个性化覆盖，把 ID 加入 `agent.catalog`，并在账号绑定表中建立显式绑定。运行时会将它与 `agent.default` 递归合并，列表配置由个性化配置整体覆盖；无需复制通用 Prompt、关系策略或记忆实现。

## 当前约束

- 先接通现有单 QQ 账号，再接 B站。
- NapCat 登录态必须保留，部署不得重启或重建 NapCat。
- QQ 白名单沿用现有 Nacos 配置；私聊 24 小时被动回复，主动联系只在 AI 工作作息内。
- QQ 空间遍历全部好友，并按该 AI 与每个人的多维关系分别判断点赞和评论。
- 禁止工具删除消息、修改账号资料、读取或导出凭据。

## 本地启动

```bash
docker compose -f deploy/docker-compose.yml up -d
```

生产部署不能通过初始化脚本覆盖服务器现有白名单，也不能重启或重建 NapCat。

技术栈：Python 3.11、PostgreSQL/pgvector、NATS、Nacos、Docker Compose、NapCat、OBS、Live2D、GPT-SoVITS。
