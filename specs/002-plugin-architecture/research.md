# Research: 插件化实施决策

日期：2026-09-15。依据当前未提交工作区、两项只读研究（运行时/状态、打包/UI）及官方资料。未知技术选择已形成下列决策；未运行业务测试，不把静态耦合或测试替身推断为生产故障。

## R1 — 当前契约，不建设版本兼容系统

**Decision**：插件声明只有 ID、能力、配置、权限、隔离和状态交接；使用一套当前契约。保留必要的 schema 校验，拒绝无效输入；无版本字段、范围协商、历史接口或自动转换。

**Rationale**：落实用户最新要求，独立升级用实现替换即可。包构建必需的元数据不参与管理器选择；配置修订/活动代次只用于并发控制。

**Alternatives considered**：SemVer 协商、兼容矩阵、多版本加载均排除。取消稳定契约也不可取，会破坏核心只依赖接口的硬要求。

## R2 — 真实 wheel 与独立依赖环境

**Decision**：分别打包 contracts/core/platform/host 和每个插件，使用唯一顶层包名。保留 Python entry point 发现思路，发现期只读 JSON/元数据，装载前核验来源和摘要。worker 使用独立环境，核心环境不安装供应商包。

**Rationale**：当前 pyproject `packages=[]` 仅提供 entry point 元数据，Dockerfile 后 COPY 源码才能运行；requirements 把所有供应商依赖装入共享 base，不能证明独立交付。entry points 可以发现独立安装分发中的组件，但不会自行提供完整生命周期。[PyPA 插件发现指南](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)

**Alternatives considered**：整仓 wheel+extras 仍联合发布；保留源码 COPY 仍绕过产物验证；向核心解释器 pip install 会改变其他能力环境。

## R3 — 通用宿主、可撤销能力句柄与资源 Scope

**Decision**：一个通用 host 包按部署 role 加载配置和管理器；能力引用为可撤销代理，实例拥有全部 tasks/jobs/subscriptions/clients。

**Rationale**：Gateway 仍有 QQ 分支，AI Agent 直接组装 Memory，ExtensionHost 直接组装 MCP/Grounding。AIRuntime 的 `_in_flight` 不是全部后台工作账本；Memory 的 module.stop 不能代替新独立插件的完整资源回收。

**Alternatives considered**：仅搬目录、仅复用 Runtime.drain、所有插件共用原始 scheduler/bus，均不能证明独立停用。增加中央管理微服务没有必要。

## R4 — 受控代码替换与 worker IPC

**Decision**：Memory 与纯策略可信进程内；依赖冲突/资源风险能力使用独立解释器 worker，双向带长度 JSON 帧，通过宿主代理访问资源。进程内代码变化允许宿主受控重启；不可信代码需要实际操作系统隔离，无法提供则拒绝。

**Rationale**：Python reload 不替换所有外部旧对象引用；故不能把删除模块缓存作为可靠卸载。进程内只能证明管理引用与资源归零，物理代码回收需进程退出。[Python 3.11 importlib.reload](https://docs.python.org/3.11/library/importlib.html#importlib.reload)

**Alternatives considered**：全部进程内不能隔离依赖；普通子进程不是安全沙箱；Memory 微服务违反同进程约束。IPC 不采用 pickle，避免传送任意 Python 对象和执行语义。

## R5 — 私聊一致性留核心，扩大动作许可覆盖

**Decision**：保留入站去重、联系人→任务→发送锁顺序、准备快照、`(ai_id, account_id, run_id)` 发送键、摘要、领取代次及 unknown 状态。平台插件只执行已授权的固定目标命令。群聊、QZone 和直播动作另接入通用动作许可/记录，不假定私聊账本已经覆盖它们。

**Rationale**：真实链为 GatewayMessageHandler→PrivateInteractionRepository→NATS→AIRuntime/PrivateReplyService→SocialSendHandler→SocialDeliveryRepository→Channel.send。当前 `claim_version` 是领取 fencing，不是插件版本。送达确认丢失不能自动重发。

**Alternatives considered**：将账本私有化到 channel 插件会阻碍替换；所有异常一律重试破坏现有未知结果约束。

## R6 — 控制面短事务与 Memory 联合恢复

**Decision**：PostgreSQL 保存操作和绑定，以行锁/条件更新在一个事务提交活动代次。Memory 延用 JetStream KV CAS，切换先停止旧写入，再导出数据库和 KV/consumer 共同静止点；不能证明静止就阻断并恢复宿主。

**Rationale**：现有 Memory 同时包含数据库文档和两个 KV 状态集合。NATS KV 有条件更新能力，PostgreSQL 有事务锁，但这不构成跨系统事务。[NATS KV](https://docs.nats.io/learn/key-value/)、[PostgreSQL 锁](https://www.postgresql.org/docs/current/explicit-locking.html)

**Alternatives considered**：只保存数据库备份、换插件时重建 durable、管理器持久记录和绑定分开提交，都不能作为完整恢复方案。不增加分布式事务协调系统。

## R7 — 声明式 UI 与双向 MCP 归属

**Decision**：控制台保留登录/管理外壳，插件贡献为通用 schema+查询/动作引用，固定 `/extensions/:contributionId/*` 路由。MCP 服务端继续单部署代理目录；现有 MCP 客户端能力单独成为 tool-mcp-bridge 插件。

**Rationale**：app.tsx/navigation.ts 静态 import 业务页，后端 app.py 实例化记忆 reader；只改后端不能达到无前端重打包的移除。MCPToolProvider 客户端方向不同于 MCP 服务端，必须明确迁移归属；清单最终为 31 包。

**Alternatives considered**：每插件添加 React import 不独立；任意远程 JS/Module Federation 当前无必要。把 MCP 客户端藏回核心会保留具体组装依赖。

## R8 — 正式入口验证与现有功能上限

**Decision**：保留现有测试作回归素材，新增完整 host→WS→NATS→持久任务→发送测试和无源码 wheel 验收。模型/平台用边界模拟；单独报告真实环境验证。音乐、Avatar、Stream 当前日志/占位能力只迁移已有行为并明确 unavailable/unsupported，不新增播放器或 OBS 驱动。

**Rationale**：private_reply_fixtures 使用真实本地 PostgreSQL，但 LocalBus、MockTransport、SimpleNamespace runtime 与私有 channel 入口替代部分真实链；既有私聊负载的 10 会话、1 条/秒、600 秒不等于新规格指标。live/avatar 和 stream 当前回调仅日志。

**Alternatives considered**：把现有回归通过当插件验收、用测试包替代全部实际插件、顺带开发真正舞台输出都会产生错误的完成结论或扩大范围。

## 已解决与实施时测量

无 NEEDS CLARIFICATION 待决技术项。基线机器规格、依赖锁解析结果、真实性能和恢复时间在实施时采集，不作为未决架构问题。技术决策不等于已达到运行目标；最终仍以 acceptance.md 的逐插件证据为准。
