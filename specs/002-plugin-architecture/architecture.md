# AI-Love 插件化重构：架构与迁移设计

日期：2026-09-15。配套需求：[spec.md](spec.md)。本文是基于当前工作区的目标设计，尚未实现，也不表示生产故障或验收已被复现。

## 1. Core vs plugin 边界分析

### 1.1 架构结论

采用“小核心 + 稳定契约 + 能力注册表 + 受管插件实例”。核心持有人物和动作的不可破坏规则，插件提供可变能力。复用现有 Provider、entry point、AgentSupervisor 的思路，但统一装载、资源归属和切换语义。

核心、契约 SDK、插件各自发布。新增插件只交付该插件的产物和配置；不能修改核心代码、核心依赖锁、硬编码注册表或其他插件。首期定义现有变化点后，同一扩展点的新实现无需核心发布；真正新增一种契约语义属于显式契约演进，不能包装成“新增实现无需改核心”的例外。

```text
部署清单 ──> 通用宿主 ──> 核心（管理器、协调、授权、路由）
                              │               │
                              v               v
                         契约 SDK <────── 各插件
                              ^
                         平台资源适配层

禁止：核心 ──> 具体插件；插件 A ──> 插件 B 的实现或私有表
允许：插件 A ──> 已授权的能力契约 ──> 运行时选定的插件 B
```

通用加载器根据经过验证的发布清单解析工厂，是基础机制；不得在加载器、宿主入口或默认配置模型里写 `if plugin_id == ...`。核心的默认降级只产生统一的不可用结果，不构造默认供应商。

### 1.2 现状证据与真实路径

以下为静态源码可确认的架构耦合，不将它们直接认定为生产运行故障。所有链接相对本规格目录指向工作区源文件；文件可能随用户现有修改继续变化。

| 真实入口/来源 → 组装及使用路径 | 已有边界与当前限制 | 目标归属 |
|---|---|---|
| [service.gateway 配置](../../deploy/nacos/service.gateway.yaml) `accounts[].adapter=qq` → [GatewayService.on_start](../../gateway/gateway_service.py) → DriverManager → [QQChannel](../../gateway/qq_channel.py) WebSocket 接收、归一化 → GatewayMessageHandler → 社交总线 | Channel 已可发现；宿主仍有 `adapter == "qq"`、QQ 超时注入、白名单同步和 `_schedule_qzone` 组装 | Channel、QQ 同步和 QZone 实现进入插件；账号归属、通用入站/发送协调留核心 |
| [AIAgentService.on_start](../../agent/ai_agent_service.py) → 直接 MemoryModule.start → AgentSupervisor.reconcile → AIRuntime.start | [AgentSupervisor](../../agent/agent_supervisor.py) 有 Runtime Protocol、替换和排空；是人物配置生命周期，不是插件管理器 | 保留人物协调能力，注入受管能力句柄；Memory 是独立发布的可信进程内插件 |
| [AIRuntime.start](../../agent/ai_runtime.py) → 全局设置/人物定义 → ChatAgent、视觉、TTS、主动私聊等构造 → handle_social / handle_live / send_response | TTS 使用 DriverManager，但构造参数由宿主预设；AIRuntime 直接使用 `_host._db`，组装大量策略和供应商适配 | 稳定回合协调留核心；生成、视觉、语音、社交策略进入插件；共享状态访问改为公开端口 |
| [create_chat_model](../../shared/chat_model_factory.py) → 配置 `provider` → [CHAT_MODEL_STRATEGIES](../../shared/chat_model_strategy.py) | 工厂输入来自有效模型配置；全局字典及供应商 SDK import 绑定 DeepSeek、Anthropic、OpenAI | 每个模型适配独立插件；LangChain 适配对象不得出现在核心契约 |
| AIRuntime.start → [load_toolset](../../agent/extension_toolset_loader.py) → tool.list.request → [ExtensionHostService](../../extensions/host/extension_host_service.py) → ToolGateway → MCPToolProvider | 已有 ToolProvider、按 AI 授权、永久禁用动作；宿主直接组装 Grounding/MCP，发现缓存和工具快照缺少统一代次管理 | 复用授权语义，提供受管能力目录和失效通知；不能把“发现一次”当动态插件生命周期 |
| [MCP 服务模块](../../extensions/mcp/mcp_server.py) import → register_weather/music/web_search；lifespan 构造天气和搜索资源 | 工具与客户端的集中导入、注册、资源模型决定增加工具仍需改宿主 | 三个工具分别发布；一个通用 MCP 接入进程代理受管工具目录，保持单一 MCP 部署 |
| [MemoryModule.start](../../memory/memory_module.py) → MemoryStateStore/MemoryPipeline → 持久活动订阅及两类定时扫描 | 已有 KV revision/CAS、活动水位和批处理，不应重写丢弃；模块同时组装记忆、关系、表情和清理任务 | 首次整体包装；随后按记忆、关系、表情能力拆分，资源归属和写入所有权必须随之拆分 |
| [GPTSoVITSService](../../gptsovits/gpt_sovits_service.py) → 引擎配置 → DriverManager → SynthesisService | SpeechEngine 已有 synthesize/close，仍由宿主构造具体 HTTP 参数 | 稳定语音端口 + 各引擎插件拥有配置和连接 |
| [LiveEdgeService.on_start](../../live/edge_service.py) → `[AvatarModule, StreamModule]`；导演服务 → 本地策略 | 模块有 start/stop 和部分启动失败清理，但候选模块硬编码 | Avatar、Stream、导演策略通过能力发现 |
| [控制台后端](../../admin/console/backend/app.py) 注册固定路由和 reader；[前端](../../admin/console/frontend/src/app.tsx) 静态导入记忆页 | 新业务页面目前需要主应用重新打包；可观测读取与具体存储相连 | 登录与管理外壳留核心；业务数据通过查询端口，插件页面采用通用声明式贡献 |
| [pyproject.toml](../../pyproject.toml) 单包 entry points + `packages=[]` → [Dockerfile](../../deploy/Dockerfile) 安装元数据后 COPY 源码 | 现有镜像启动依赖源码复制；不能据此证明独立 wheel 可交付 | 核心和每插件构建真实 wheel、独立依赖；无源码挂载的产物测试 |

现有测试如 [test_private_reply_flow.py](../../tests/test_private_reply_flow.py) 经事件模型转换后调用 channel 内部处理入口；它覆盖部分真实处理链，但不能证明公开装载、实际 WebSocket、NATS 生命周期和部署可用。后续验收补齐这些入口，不把 mock 的模型或发送结果描述为真实平台验证。

### 1.3 所有权划分

| 边界 | 保留职责 | 禁止依赖 |
|---|---|---|
| `contracts` | 插件元数据、生命周期、能力 DTO、错误、作用域和事件语义 | 供应商 SDK、数据库 ORM、NATS/MCP 客户端、插件实现、宿主类 |
| `core` | 管理/诊断、能力绑定、生命周期与操作日志、权限、事件顺序、任务/订阅资源账本、受众与身份不变量、动作幂等协调 | 任何具体插件或插件专属配置类型；不经公开端口直接读插件表 |
| 平台资源层 | 现有配置来源、消息传输、持久存储、日志、时钟、调度器的契约适配；保证最小管理路径启动 | 业务插件 import；把通用对象连同无限权限交给插件 |
| 业务插件 | 平台协议、生成实现、模型适配、语音、视觉、记忆处理、关系演进策略、表情、工具、主动社交、直播实现 | 核心私有属性、其他插件的 Python 对象、绕过动作授权和数据归属规则 |
| 发布配置 | 可用插件、产物位置及摘要、启用范围、能力绑定、允许权限、工作进程分配 | 可执行代码、核心源码注册列表、隐式安装最新实现 |

平台资源层是现有基础设施的适配实现，核心只消费其公开端口；本次不将 PostgreSQL/NATS/Nacos 服务器的更换或管理认证的替换也定义成业务插件。它不允许容纳供应商模型或平台业务逻辑。即使仍使用同一数据库，插件数据也不能变成公开的共享实现接口。

长期身份、消息/发送账本、账号归属和数据所有权由核心契约约束。记忆内容和关系文档是用户持久数据，不是可随插件删除的缓存。算法和仓储适配可以替换，用户数据的稳定语义必须保持。

## 2. 插件契约与扩展点

### 2.1 发布声明、运行实例和发现

插件发布物携带不可执行的 `plugin.json`、wheel 和独立依赖锁。包由发布工具安装到固定的插件位置，运行时不会根据外部输入任意下载/安装代码。发现阶段读取元数据，不 import 插件；先校验摘要、信任来源、能力依赖图及权限，再装载工厂。不维护插件版本目录或兼容矩阵。

示例是目标契约草案，路径和值均为设计示例：

```json
{
  "id": "ailove.channel.qq",
  "entrypoint": "ailove_plugin_qq:create_plugin",
  "provides": [{"capability": "channel"}],
  "requires": [{"capability": "identity.lookup", "optional": false}],
  "instance_scope": "account",
  "config_schema": "schemas/config.json",
  "state": {"namespace": "ailove.channel.qq", "transfer": "channel-state"},
  "isolation": "worker",
  "upgrade_mode": "drain-and-replace",
  "permissions_requested": ["channel.receive", "channel.send", "identity.lookup"],
  "limits": {"max_inflight": 20, "queue_capacity": 200},
  "ui": [{"kind": "status", "capability": "channel"}]
}
```

- `id` 是逻辑实现身份，`instance_id` 由管理器生成，不能与人物 `ai_id` 混用。发布清单的产物位置和摘要只用于交付与核验内容，不进行版本比较或选择。
- 提供/依赖声明只使用能力名，不声明版本范围，也不引用另一个插件包；清单的绑定配置允许运维显式选定具体实例。
- 提供者必须满足能力语义而非只有相同方法名；插件契约测试随 SDK 提供。
- 显式配置绑定胜过自动解析；未绑定时只接受唯一能力提供者，多个候选报冲突。策略列表使用有序绑定，不按目录扫描顺序碰运气。
- 缺失可选能力产生标准 `unavailable`；缺失必需能力阻断相关插件/业务范围，不能让整个管理面无法启动。
- 包内 entry point 可统一为 `ai_love.plugins`；旧分组的读取放入临时迁移适配器，最终删除。Entry point 是发现机制，生命周期由管理器定义。[PyPA 规范](https://packaging.python.org/en/latest/specifications/entry-points/)

### 2.2 最小接口草案

以下只描述公开形状，具体 DTO 字段在规划阶段整理为当前契约文件；不会直接作为本次可运行代码交付。

```python
class Plugin(Protocol):
    async def init(self, context: PluginContext) -> PreparedCapabilities: ...
    async def start(self, activation: ActivationContext) -> Ready: ...
    async def stop(self, request: StopRequest) -> DrainReport: ...
    async def dispose(self) -> DisposeReport: ...

class PluginLoader(Protocol):
    async def load(self, artifact: VerifiedArtifact) -> PluginHandle: ...
    async def unload(self, handle: PluginHandle) -> UnloadReport: ...

class CapabilityDirectory(Protocol):
    async def acquire(self, capability: CapabilityRef,
                      context: InvocationContext) -> CapabilityLease: ...
```

load/unload 是管理器调用加载器的动作，init/start/stop/dispose 是插件钩子。不能让插件自己卸载自身或关闭共享宿主。健康、配置预检、状态导出/导入是明确的附加契约；所有插件均提供配置预检，有状态插件必须提供状态交接能力，无状态插件显式声明 JSON `state: null`。

`PluginContext` 只包含该实例的只读配置快照、作用域、经过限制的日志/指标、能力代理、资源 Scope、调度、存储/事件/网络端口。它不含 `host`、服务定位器、完整数据库 Session、Nacos client、无限 NATS bus、任意文件系统或进程环境。

`InvocationContext` 包含请求/事件 ID、可信 `ai_id/account_id/person_id/conversation_id`、受众、deadline、取消信号、授权修订和幂等键。管理器另附不可伪造的身份凭证及活动代次。DTO 使用可序列化的值和显式 schema；不传 `BaseChatModel`、`StructuredTool`、ORM 实体或异常对象。插件内自行适配 LangChain 等库。

业务响应统一为成功数据或 `PluginError`，包含 code、retryable、side_effect_status（none/committed/unknown）、安全描述及 correlation_id。堆栈只进入受控日志。同步签名、异步流、取消、错误和交付语义均属于契约，不能只约定函数名称。

### 2.3 首批扩展点

| 能力 | 输入 → 输出 | 范围/选择与缺失行为 |
|---|---|---|
| `channel` | 平台事件 → SocialMessage；ResponseCommand → DeliveryReceipt；能力探测 | 每账号一个活动实现；缺失暂停该账号收发；不声称维持平台未持久接收消息 |
| `content.normalize` | 标准内容片段与引用事实 → 类型/结构，禁止发送动作 | 每渠道有序策略，保留当前 quote/forward/voice/image/file/at/text 顺序；每个独立 entry point 最终独立发布 |
| `conversation.generate` | 回合、上下文、工具 schema → 流式/完整响应计划及用量 | 每 AI 选择实现；现有 LangChain 编排封装为插件，核心验证最终动作 |
| `model.generate` | 标准多模态消息、工具声明、生成预算 → token/工具意图/用量 | 按配置顺序故障切换；OpenAI/Anthropic/DeepSeek 独立适配；不把模型 SDK 对象交给消费者 |
| `media.describe` | 带来源的图片/语音资源描述 → 理解结果和依据 | 缺失时只处理已支持输入，禁止虚构理解；ASR 仅在实际接入时提供实现 |
| `speech.synthesize` | 人物声音配置与文本 → 音频引用/格式/时长 | TTS 客户端和后端引擎通过契约连接；无语音时仅在业务允许时降级文本 |
| `memory` | 查询/已持久化活动 → 检索结果；静默 Episode/Atom/文档演进 | 每状态范围只有一个写入者；可信进程内；停用暂停依赖记忆的业务和归并，积压按预算保留 |
| `relationship` / `sticker` | 互动事实/表情素材 → 关系视图/候选表情 | 关系按 AI+person，表情检索失败可省略表情；不把一个人的关系扩散给他人 |
| `social.policy` | 只读回合/关系/作息快照 → 参与、重复、主动联系或评论意图 | 首期覆盖现有社交策略；禁用主动策略即不产生主动意图，被动能力单独绑定 |
| `tool` | 已授权工具调用 → 结构化结果和副作用状态 | 多提供者，工具 ID 唯一；保留 Grounding、天气、音乐、搜索各实现 |
| `live.director` / `avatar` / `stream` | 场次/观察或舞台指令 → 决策/确认 | 每场次/输出设备绑定；失去必需能力暂停相关输出，不自动重复推流动作 |
| `ui.contribution` | 声明式状态卡、配置 schema、操作引用 → 通用管理页面 | 多实例贡献，路由归通用命名空间；停用撤销，历史诊断保留 |

核心不提供“任意前后钩子”；输入处理、决策和动作授权顺序固定。插件输出意图后必须经过核心受众/权限/幂等校验。社交策略不能接管身份归属，模型不能提升工具权限。

插件间持有可撤销的 CapabilityLease，而不是永久缓存提供者对象。普通请求固定一次配置和路由代次；跨多个能力的回合固定同一组绑定快照。权限撤销是例外，发出副作用之前必须重新校验当前授权。工具目录变更发布修订通知，下一回合取新快照，旧工具引用不可绕过停用检查。

## 3. Plugin Manager 与生命周期

### 3.1 状态与资源归属

```text
DISCOVERED --load--> LOADED --init--> INITIALIZED --start--> RUNNING
RUNNING --stop（关入口、排空）--> STOPPED --start--> RUNNING
INITIALIZED / STOPPED --dispose--> DISPOSED --unload--> UNLOADED
LOADED --unload--> UNLOADED
任何阶段失败 --> FAILED（阶段、剩余资源、可重试/需重启）
```

`enabled` 是期望配置，不是上述生命周期状态；停用执行 stop→dispose→unload，仍保留安装包和持久数据。remove 在卸载成功后才移除安装记录与包文件。再次启用重新实例化。FAILED 不是已卸载，必须完成补偿或进入需宿主恢复状态。

| 动作 | 前置条件与行为 | 完成标准及异常处理 |
|---|---|---|
| load | 已验证发布物、已获准的隔离模式；启动 loader/worker 并解析工厂 | 尚无业务路由；import/工厂失败清理部分进程和句柄，其他实例不变 |
| init | 注入限定 Context，校验配置、准备依赖和资源，不消费外部输入、不提交用户数据 | 提供候选能力；初始化失败回收 Scope，尽力 dispose 后 unload |
| start | 候选绑定已准备；启动资源并报告就绪，候选入口及定时工作受激活闸门阻挡 | 健康检查通过后，管理器提交唯一活动代次/租约并开放工作；失败撤销候选，补偿部分启动 |
| stop | 先撤销新请求入口/定时触发，保留在途请求必要的出站能力；按截止时间排空和检查点 | 归零或明确取消/未知结果，最后撤销出站许可和资源租约；超时标记失败，不假装成功 |
| dispose | 已停止/初始化失败；按 Scope 逆序释放本实例资源，所有回收动作幂等 | 资源账本归零；不得关闭其他实例连接、删除持久表、清理 NapCat 登录态 |
| unload | 无活动业务引用/资源；工作进程终止并回收；进程内释放管理器引用 | 报告 logical-unloaded 或 process-unloaded；需要更换代码时依隔离模式处理 |

资源 Scope 包括 HTTP/文件句柄、定时器、任务、订阅、RPC responder、缓存、可撤销代理和 UI 注册；借用的共享资源只归还引用，不由插件关闭。禁止插件自行创建未登记的后台循环。进程内插件违约时无法可靠强杀任意 Python 代码，只能封禁新流量并执行宿主恢复；这类限制不能伪装成安全沙箱。

### 3.2 顺序、并发与恢复

1. 对能力依赖拓扑排序：依赖先 init/start，消费者先 stop/dispose。候选依赖图有环、重复绑定或缺少必需能力时整体预检失败。
2. 管理入口接受 `operation_id`、期望修订和目标范围，同一实例串行；依赖图变更在受影响子图使用固定锁顺序，避免死锁。多个管理副本通过持久 CAS/租约只允许一个提交者。
3. 持久记录 prepared → quiesced → committed → cleaned 阶段、发布摘要、配置/授权/路由修订与状态水位。每步重复执行返回同一结果。
4. 重启读取最后提交代次；未提交候选清理，已提交候选继续完成清理。旧实例凭证必须过期或被 fencing 校验拒绝，不能靠“进程大概已经退出”维持单写者。
5. 排空覆盖前台请求、私聊扫描、主动联系、Memory 两类归并扫描、定时清理和事件回调，不能只沿用 AIRuntime 的一个前台计数。
6. 核心存活、管理就绪、某能力就绪分别报告。必需业务插件失败影响该业务的 readiness，不抹掉管理面的故障诊断能力。

### 3.3 升级、替换与单写者

无状态且可并行准备：校验候选 → load/init → start（候选入口冻结）→ 健康预检 → 提交路由代次并开放激活闸门 → 新请求走新实现 → 旧请求排空 → dispose/unload 旧实现。候选健康预检不得产生对外动作。start 返回就绪不等于插件有权自行开始消费或执行定时动作。

渠道连接、记忆和主动任务等有状态单写者：准备候选 → 关旧实现新入口 → 排空/检查点 → 撤销旧写入代次 → 校验并移交状态 → 候选 start 就绪 → 提交新代次、开放新路由和工作闸门 → 清理旧实现。权威活动代次、绑定和操作提交在同一持久事务记录中更新；路由副本未同步时拒绝旧代次写入，不能各自猜测活动实例。中间短暂停顿由已持久工作队列承接；未被平台可靠重放的输入必须在切换前报告风险并安排维护窗口。

核心动作网关和存储写入边界校验代次、幂等键及 owner；只在管理器内存里记一个 active 标志不足以阻止旧 worker。对本地/远程执行的非幂等外部动作，先记录发送意图，再记录确认；确认未知进入查询/人工处理，禁止自动双发。平台不提供幂等/查询能力时不承诺网络故障下的端到端 exactly-once。

恢复分两种：提交前失败清理候选并保留原实例；提交后按本次变更预先定义的数据恢复步骤处理，保留实际副作用记录和已确认状态，不直接把旧对象重新塞回字典。恢复不依赖插件版本历史或自动转换机制。撤掉唯一必需能力的操作默认预检失败；管理者明确选择“停用相关业务范围”后可以继续，必须保留核心管理可用。

## 4. 配置、权限、隔离和错误处理

### 4.1 配置和独立交付

- 沿用 Nacos 来源：已有 `agent.default` / `agent.<ai_id>`、`service.*` 保存人物与部署配置；新增插件配置命名空间，不把所有插件字段塞回 `GlobalSettings`。
- 通用实例记录只认 `plugin_id`、产物位置/摘要、enabled、scope、config_ref、授权引用及能力绑定；插件自带 schema 校验私有配置。
- 目标覆盖顺序：插件默认值 → 服务范围 → AI/账号范围；标量替换、对象按键合并、数组整体替换、删除使用显式移除标记。既有 Agent 定义使用 deepmerge；不能仅依据 README 推断实际数组语义，迁移先做配置样本特征测试，再产出明确转换。
- 配置更新先校验完整候选快照、依赖和权限；成功才原子提交修订。无效、乱序、重复更新不会破坏当前实例。权限独立管理，配置不能把 requested 变成 granted。
- 允许插件声明可热更新字段；其他字段使用受控替换。每请求保留配置修订，操作记录保留前一快照，不在日志记录正文或凭据。
- 独立 wheel/锁只安装在该插件环境，禁止运行期 `pip install` 到核心解释器。按指定产物位置交付并核验摘要。宿主可使用插件目录挂载或独立 worker 产物，升级不重建核心产物。

### 4.2 当前契约与实现替换

按用户要求不设计插件版本管理、API 版本协商、配置/状态格式版本号、兼容矩阵、历史接口支持或自动兼容转换。所有插件直接遵循当前公开契约；配置 schema、生命周期入口检查和契约测试仍用于验证实际行为。

升级就是交付该插件的新实现并完成 load/init/start → 切换 → stop/dispose/unload。切换期间可暂存候选和原实例以便排空，但不提供多版本选择、范围解析或历史版本仓库。作者负责让替换实现遵守当前契约；新实现未就绪时保留原实例。

Python 构建工具要求的包元数据由打包工具处理，插件管理器不读取其版本来决定装载。产物摘要用于完整性核验；实例代次用于防止旧实例继续写入；配置修订用于避免并发覆盖。这些标识不承担插件版本管理功能。

事件 envelope 包含 `event_id/occurred_at/trace_id/scope/config_revision/producer_generation`。订阅方按当前契约解析；无效持久事件保留并报告，不默默跳过。NATS subject 和 HTTP/MCP 映射使用当前契约，不维护历史协议适配层。

### 4.3 数据所有权与迁移

- 核心状态端口维护身份、账号、会话和发送账本的统一语义。插件只能按授权范围调用；关系/记忆通过公开查询和写入协议读写，不能让控制台或其他插件直接依赖 ORM 模型。
- 插件私有运行数据进入独立 schema/命名空间；migration 随插件发布并用迁移锁独立登记。沿用 Alembic，但不能让每个插件的新 revision 都要求修改核心的中央迁移链。
- 现有共享表先保持唯一所有者，通过当前公开端口访问；不先拆数据库。数据迁移采用 expand → backfill → switch → contract，回退窗口结束前不删旧字段。
- 替换实现支持标准快照及增量水位（含 ai/person/account/conversation ID、来源、状态内容、未完成工作和幂等记录）。候选先导入到暂存范围；最终交接时排空旧写入并对齐水位，不允许两个实现同时合并同一人物记忆。
- 已知 Memory 状态含数据库 Episode/Atom/文档和 JetStream KV 活动/待合并状态；恢复验证必须覆盖两者的共同一致点，不能只备份数据库。持久 consumer 水位、租约和幂等键不因插件实现替换而重置。
- 插件移除只卸载执行能力，保留数据目录、迁移历史和导出读取能力说明；擦除数据另行鉴权执行。

### 4.4 权限

授权取“宿主允许 ∩ 组织/操作者策略 ∩ 插件申请 ∩ 实例范围 ∩ 当前调用范围”。声明式权限必须由宿主代理执行，不能只靠插件自觉。

- 管理操作先复用控制台鉴权；安装和升级只能引用批准的产物位置，不能把用户输入直接拼成模块路径或命令。
- 工具永久禁止删除消息、修改账号资料、读取/导出凭据。现有 allow/conditional/confirm/deny 需映射成明确判定：conditional 必须有实际条件判定，confirm 没有可信确认记录就拒绝，不能把标签当授权。
- 模型不能选择任意 `ai_id` 或账号；来自已认证入口的身份与核心绑定记录确定作用域，插件自报字段只作为待校验数据。
- 网络访问通过主机/方法允许列表、超时与响应大小限制；存储路径限制在实例范围；事件只允许列出的 subject；资源预算按实例计量。
- 供应商凭据由受限连接代理或隔离 worker 的最小环境注入；工具参数、输出和日志不能读取凭据。进程内可信插件没有真正的环境隔离，不能用它承载不可信工具代码。
- 审计记录 actor、operation_id、插件/实例、作用域、配置/权限修订、允许或拒绝原因，默认不记录消息正文。

### 4.5 隔离和 Python 卸载的现实边界

| 模式 | 适用 | 独立升级/卸载保证 |
|---|---|---|
| trusted-inprocess | 保持同进程的 Memory、审核过的轻量策略 | 可撤销路由、排空、释放实例；代码或依赖更换采用声明的宿主维护重启，不保证解释器清除所有模块引用 |
| worker | 供应商 SDK、渠道连接、工具等需要独立依赖或硬停止的插件 | 独立环境/产物，停止进程树后物理回收；可以在核心进程存活时更换 worker |
| restricted worker/container | 未被信任或需要更强文件/网络/资源边界的代码 | 最小凭据、操作系统权限、网络/挂载限制和资源配额；无法建立隔离时拒绝执行 |

普通子进程继承相同系统权限并不构成安全隔离。Windows 开发和生产 Linux 的隔离实现不同，但必须报告同一套实际保证；本地未能提供强隔离时只接纳可信插件，不谎报验证通过。

不使用 `importlib.reload` 或删除 `sys.modules` 作为热卸载保证：旧实例和外部引用可能继续保留旧对象。Python 官方列出的 reload 限制支持这一判断；因此进程内“逻辑卸载”和进程退出后的“物理卸载”必须分开报告。[Python importlib](https://docs.python.org/3/library/importlib.html#importlib.reload)

Memory 的同进程要求来自宪章，采用后者的受控宿主重启路径；其他插件产物不改，但同宿主实例会有计划内暂停。独立交付不等于所有插件始终零停机。若以后要求 Memory 在核心不重启时也能隔离任意依赖和故障，需要另行修改这一架构约束，不能在本次静默改成微服务。

### 4.6 错误、投递与可观测性

| 错误类别 | 标准处理 |
|---|---|
| manifest_invalid / dependency_conflict / config_invalid | 装载前拒绝，保留原实现，提供具体字段/依赖边 |
| permission_denied / scope_mismatch | 不重试，审计；不把错误转交模型后允许其扩大权限 |
| capability_unavailable / dependency_stopped | 已声明的降级或暂停，返回可定位错误，不静默成功 |
| timeout / overloaded / provider_failed | 在调用总预算内有限重试、退避及熔断；队列满明确背压 |
| side_effect_unknown | 记录未知，按幂等键查询确认或人工处理，不盲重试 |
| lifecycle_failed / drain_timeout / cleanup_incomplete | 撤销新入口、限制故障扩散，展示残留资源，按隔离模式恢复 |
| state_transfer_failed / migration_failed | 不提交新写入者，保留备份和恢复信息 |

只读幂等调用默认最多重试 2 次，所有尝试受同一 deadline 限制；模型故障切换沿显式顺序，并且副作用已提交/未知时不能整轮重新生成后再次执行。并发/队列上限使用清单与运维授权中更严格值。

控制阶段默认 30 秒，stop 排空默认 60 秒，超时返回明确状态。有状态导入的 deadline 由预检按数据量给出，不藏在固定初始化超时中。Memory 停用后停止确认尚未持久处理的活动，保留原有持久水位；持久积压达到容量阈值时告警并暂停依赖流程，不能因为“插件可拔掉”就丢弃数据。

健康与指标最少包括实例/代次、实际/期望状态、在途数、队列深度与最老任务年龄、调用延迟/错误、重试/熔断、拒绝授权数、清理残留、状态恢复水位、模型调用/token。每种告警对应恢复步骤。验收负载和目标见 SC-006/007，当前没有实测数据。

## 5. 推荐目录结构

```text
ai-love/
├── packages/
│   ├── contracts/                 # 独立 SDK：src/ailove_contracts、schemas、契约测试
│   │   └── pyproject.toml
│   ├── core/                      # src/ailove_core
│   │   ├── pyproject.toml         # 无任何业务插件及供应商依赖
│   │   └── src/ailove_core/
│   │       ├── plugins/           # manifest、manager、lifecycle、registry、scope
│   │       ├── identity/          # 不变量、公开状态端口
│   │       ├── turns/             # 顺序、路由、响应/动作协调
│   │       ├── permissions/
│   │       └── operations/        # 控制面、审计、健康
│   └── platform-runtime/          # Nacos/NATS/Postgres/Redis/telemetry 端口适配
├── hosts/
│   ├── gateway/                   # 通用入口，只读发布清单并启动管理器
│   ├── ai-agent/                  # Memory 仍在此宿主进程内
│   ├── speech/
│   ├── extension-host/
│   ├── mcp/                       # 单一 MCP 入口，通用工具目录代理
│   ├── director/
│   ├── live-edge/
│   └── admin/                     # 登录、管理外壳和声明式渲染
├── plugins/
│   ├── channel-qq/
│   ├── content-quote/             # forward/voice/image/file/at/text 各自同结构
│   ├── conversation-langchain/
│   ├── model-openai/              # model-anthropic、model-deepseek 同结构
│   ├── speech-gptsovits-client/
│   ├── speech-gptsovits-engine/    # speech-mimo-engine 同结构
│   ├── media-vision/
│   ├── memory-default/            # migration、state transfer、真实入口回归
│   ├── relationship-default/
│   ├── sticker-default/
│   ├── social-proactive/          # group-participation、group-repeat、qzone 策略等
│   ├── tool-grounding/
│   ├── tool-weather/              # tool-music、tool-web-search 同结构
│   ├── live-director-default/
│   ├── live-avatar/
│   └── live-stream-default/
├── migration-adapters/            # 仅本次重构的临时包装器，迁移结束即移除
├── deployment/
│   ├── manifests/                 # 插件产物位置/摘要、实例范围和能力绑定
│   └── local/                     # 本地验证配置；不含凭据值
├── tests/
│   ├── architecture/              # 源码与传递依赖约束
│   ├── plugin-conformance/        # 对每个产物执行相同契约验证
│   ├── integration/               # 正式宿主与业务入口
│   └── recovery/                  # 故障注入、持久数据恢复
└── specs/002-plugin-architecture/
```

每个插件目录含 `pyproject.toml`、`plugin.json`、依赖锁、`src/<unique_package>/`、配置/状态 schemas、tests、操作与迁移说明；有状态插件再含 migrations。不同插件不得使用冲突的 Python 顶层包名。目录不等于微服务，现有部署单元数量不因每个插件增加而自动增加。

正式规划以 [plan.md](plan.md) 的 31 包清单为准：补入远端 MCP 客户端 `tool-mcp-bridge`，直播统一命名 `live-avatar-default`、`live-stream-default`；各宿主入口收敛为同一 `hosts/runtime` 包，以 role 区分现有部署。Avatar/Stream 目前只有日志回调，不隐含新建真实输出驱动，未实现外部动作明确报告 unsupported。

通用业务 UI 不静态 import 插件组件：安装时注册受限 schema 和数据/操作引用，由固定外壳渲染；任意 JavaScript 远程组件不在首期范围。现有记忆/人格页面逐步改为调用稳定查询端口的声明式视图或通用页面，必须通过“移除插件无需重新打包前端”的验收。

## 6. Strangler 渐进迁移计划

这是实施路线，不替代 `$speckit-plan` 的正式 plan.md 和后续 tasks.md。先建立同一入口的可控转发，再逐步把能力移到新实现，最后删除旧路径。

| 阶段 | 操作与改动范围 | 出口证据 | 回退/退出条件 |
|---|---|---|---|
| 0. 固定基线 | 记录当前未提交修改、配置样本、依赖/产物摘要、真实入口和数据所有权；复用私聊/记忆/引用/模型故障切换测试素材，标明模拟边界 | 在本地隔离环境建立旧路径功能与负载基线、备份恢复演练 | 基线不稳定先定位；不宣称现有代码已通过生产测试 |
| 1. 抽取契约 | 从 shared/contracts、Channel、TTSProvider、SpeechEngine、ToolProvider、Runtime 整理 SDK；DTO 消除供应商/ORM 类型 | 空核心启动；core→plugin 和 SDK→实现依赖检查通过 | 契约采用新命名空间，旧调用路径仍在；此阶段不迁移数据 |
| 2. 建管理器和迁移边界 | Scope、状态机、配置校验、能力代理、操作日志、隔离 loader；旧实现在 migration-adapters 中实现相同契约 | 经管理入口覆盖全部生命周期及每阶段失败；旧业务经通用路由跑通 | 未达成清理/幂等要求不开启真实动作；切回旧路由 |
| 3. 先抽取语音与工具 | 把已有 entry points 变为真正独立产物；拆天气/音乐/搜索的配置资源；MCP 宿主只代理目录 | 单插件卸载/升级不改核心，工具列表修订在下一回合生效，其他工具不中断 | 按能力绑定回旧包装器，禁止两条路径重复执行动作 |
| 4. 抽取模型与视觉 | 移除全局供应商字典，LangChain 编排通过 model.generate 代理；视觉和多模态输出保留来源 | 相同模型响应下现有顺序故障切换、引用归属、token/调用成本不回退 | 每 AI 切回旧生成实现；已产生动作的回合不重放 |
| 5. 抽取 QQ 和内容策略 | channel 插件承接协议、配置、同步；QZone 按关系能力发出意图；移除 Gateway 中 QQ 分支 | 正式 WebSocket 入站→持久任务→Agent→发送账本→模拟 NapCat；引用/转发/重连与白名单回归 | 账号为切换范围，只有一个活跃连接/发送代次；保留 NapCat 登录态和现有白名单 |
| 6. 抽取状态能力与社交策略 | Memory 首次整体插件化且保持进程内，再拆关系/表情；消除 `_host._db` 与跨插件表访问；私聊/主动扫描纳入 Scope | 数据库+KV 联合恢复、双 AI 隔离、静默归并、停用积压及状态替换测试；排空覆盖后台任务 | expand/contract 和单写者交接；旧实现不可读新实现数据时不得直接回滚 |
| 7. 直播与控制台 | Avatar/Stream/导演策略由清单装配；管理与业务 UI 使用能力和声明式贡献 | 移除一种输出不破坏其他能力，插件页面撤销无需重打包核心前端 | 按场次/设备切换；OBS 输出仅活动路径执行 |
| 8. 收尾和产物验收 | 删除临时迁移适配器、旧集中注册、供应商字段、整仓源码 COPY 依赖，生成每插件独立发布清单 | 每个插件六项变更、空插件宿主、无源码挂载安装、依赖冲突隔离、负载/恢复验证全部有证据 | 任一插件仍依赖旧路径则不可宣布全项目完成 |

每阶段按“脱敏输入对照 → 本地正式宿主集成 → 授权环境中的受控范围 → 扩大范围”推进。对照路径只运行纯决策或回放，不执行真实发送、记忆写入、关系更新或直播控制；生成结果与旧路由对比时使用固定模型响应，另设有预算的供应商烟测。

迁移会一次性修改现有组装点、契约调用方、打包和配置格式；这是建立稳定边界的明确破坏范围。完成后新增/替换同能力插件不得再次修改这些核心点。临时包装器只把现有实现接到当前契约上，不支持历史插件接口；它们只依赖 SDK 和旧实现，核心不导入这些包装器。每阶段写出负责人、删除条件和证据，迁移完成即删除，不保留兼容层。

已有 [test_private_reply_flow.py](../../tests/test_private_reply_flow.py)、[test_private_reply_load.py](../../tests/test_private_reply_load.py)、[test_social_delivery_recovery.py](../../tests/test_social_delivery_recovery.py)、[test_memory_state.py](../../tests/test_memory_state.py)、[test_model_failover.py](../../tests/test_model_failover.py)、[test_live_edge_service.py](../../tests/test_live_edge_service.py) 可作为回归起点。测试环境须自建本地隔离数据库/NATS/模拟平台，不读取生产连接并执行写操作。本次未运行这些业务测试。

## 7. 真正可插拔的验收标准

完整逐插件执行表见 [acceptance.md](acceptance.md)。最终判据不是目录名称或接口数量，而是：固定核心二进制/产物，在没有项目源码挂载的环境中，真实入口完成每个插件的六项独立变更，保留用户状态，验证其他能力，且没有残留执行资源或隐式实现依赖。

标准 SDK 的故障插件可证明管理器机制；它不能证明现有内置插件已正确接入。每个实际插件都必须再走自己的真实装载和业务链路，并明确哪些平台、模型或数据库使用了模拟。
