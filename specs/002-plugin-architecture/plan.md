# Implementation Plan: 可独立演进的插件架构

**Branch**: `main` | **Date**: 2026-09-15 | **Spec**: [spec.md](spec.md)

**Input**: `specs/002-plugin-architecture/spec.md`；采用用户最新范围：无需插件版本及兼容性机制。

**Status**: 设计完成；2026-09-16 已同步生成 [tasks.md](tasks.md)；业务实现及运行验收尚未开始。

## Summary

把当前集中组装的业务实现迁入独立插件包。核心只依赖公开契约，负责人物/受众不变量、调用协调、权限、插件生命周期与操作日志。平台资源适配层继续使用 Nacos、NATS、PostgreSQL、Redis；插件作者依当前契约实现能力。新增、移除、替换、启停或升级插件不得修改核心及其他插件产物。

先迁移已有语音或工具形成完整的安装→启用→业务调用→停用→物理移除切片，再迁移模型、QQ、记忆、社交策略和直播。每阶段保留可验证的旧路径包装器；新旧路径仅一个可以执行副作用。最终移除包装器和整仓源码安装依赖。

不建立插件/API/配置/状态格式版本号、版本协商、兼容矩阵或历史接口适配。替换实现使用暂存候选与活动实例；产物摘要只核验文件，实例代次与配置修订只控制并发，不用于版本选择。

## Technical Context

**Language/Version**: 维持 Python 3.11；控制台沿用 TypeScript、React 和 Vite，不同时升级语言或框架。

**Primary Dependencies**: 契约层使用 Python typing/dataclasses 及现有 Pydantic 2；核心用 asyncio、importlib.metadata、标准库 CLI；通用 HTTP 控制面用现有 FastAPI。平台适配层复用 SQLAlchemy async/asyncpg/Alembic、nats-py、nacos-sdk-python、Redis、APScheduler 与 OpenTelemetry。JSON Schema 验证使用 jsonschema，在实现阶段解析并锁定依赖；模型/MCP/音频/平台 SDK 只归各插件环境。现有精确依赖以根 requirements.txt 为迁移输入，不盲目升级。

**Storage**: PostgreSQL 保存插件实例、绑定、变更日志及账号/身份/私聊任务/发送账本；JetStream 保存持久活动，KV 保存既有记忆水位及 claim；Redis 保持会话缓存。插件产物与临时交接数据使用宿主批准的本地目录。

**Testing**: pytest/pytest-asyncio；契约与静态依赖测试；无源码挂载 wheel 验收；本地 PostgreSQL/NATS/Redis 集成；模拟 NapCat WebSocket/HTTP 与模型端点；既有前端 `npm run build`，新增浏览器测试覆盖声明式插件贡献。测试替身只替代外部边界，不替代管理器、真实实例装载或整个 AIRuntime。

**Target Platform**: Windows PowerShell 本地开发；现有 Linux Docker/Kubernetes 生产目标。普通 worker 支持独立环境和进程回收；强隔离在 Linux 容器验证，Windows 无强隔离时明确拒绝不可信插件。

**Project Type**: Python 多宿主应用 + 共享契约/核心库 + 独立插件包 + 现有 Web 控制台。拆包不新增默认微服务。

**Performance Goals**: 2 AI、20 并发会话、10 入站事件/秒、15 分钟；排除外部响应等待后的 P95 增量 ≤ max(旧基线×10%,20ms)；固定响应集下模型调用/token 不增加、非注入错误为 0。控制阶段默认 30 秒、排空 60 秒；联合状态恢复 ≤5 分钟、已确认持久状态 RPO=0。100 次启停无资源残留。

**Constraints**: Memory 仍为可信 ai-agent 进程内插件；代码替换可声明受控宿主重启。不可用能力影响相关业务 readiness，零插件的管理/鉴权/诊断仍能运行。不删除用户持久数据，不重启/重建 NapCat，不覆盖白名单。不把普通子进程称作安全沙箱。仅本地操作，无外部发布授权。

**Scale/Scope**: 目标 31 个独立业务插件包，清单见下文；现有 7 个运行单元及控制台保留。只迁移当前业务：音乐播放器、实际 Avatar/OBS 输出及新平台/游戏能力不由本次重构补建；缺失实现返回 unavailable/unsupported，不伪造动作成功。

## Constitution Check

*研究前检查：PASS。设计后复核：PASS（设计层面）；实施验收未执行。依据 `.specify/memory/constitution.md` 1.3.0。*

| 原则/约束 | 设计落实与验收位置 |
|---|---|
| 持续身份 | ai_id/person_id/account_id 独立于插件实例；状态所有权与交接见 data-model.md；SC-005/008 |
| 有依据的记忆 | 保留 activity→Episode→Atom→合并；不增逐消息记忆模型调用；数据库和 KV 联合恢复；ACC-020/023/035 |
| 多人关系与受众 | 核心注入可信上下文和受众，按会话有序；插件返回动作意图；ACC-008/021/027/034 |
| 行动反馈闭环 | 发送账本、领取代次、unknown 语义保留；未接通的音乐/舞台输出不得报告真实成功；ACC-022/036/037 |
| 清晰架构与生产运行 | 契约/核心禁止传递导入插件；Memory 同进程；复用既有基础设施，worker 按需使用；ACC-001～005/016～019 |
| 真实调用链 | 新测试从公开宿主/WS/NATS/管理入口进入；现有内部方法测试仅回归素材，测试报告标注外部模拟；ACC-033～039 |
| 数据迁移与恢复 | 本次变更单独数据迁移/恢复演练；不实现用户排除的版本兼容子系统。保留配置和状态实际有效性校验，满足数据安全要求 |
| 外部写入与治理 | 只生成本地设计与任务；将来本地实现也不授权部署、消息、Nacos/K8s 写入。仓库现有未提交修改保持原样 |

用户明确排除版本和兼容性机制；宪章的恢复要求用本次变更的数据迁移与恢复方案实现，不能以此重新引入版本协商。无需新增宪章例外。当前 `setup-plan.ps1` 的 BRANCH 输出为目录回退标识 `002-plugin-architecture`，实际 Git 分支为 `main`，脚本没有切换分支。

## Project Structure

### Documentation (this feature)

```text
specs/002-plugin-architecture/
├── spec.md / architecture.md / acceptance.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── plugin.schema.json
│   ├── lifecycle.md
│   ├── capabilities.md
│   └── management.md
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
packages/
├── contracts/src/ailove_contracts/       # lifecycle、context、capabilities、events
├── core/src/ailove_core/                 # plugins、permissions、turns、operations
└── platform-runtime/src/ailove_platform/ # persistence、nats、config、sessions、workers
hosts/runtime/src/ailove_host/           # 通用 main/HTTP/CLI，role 来自部署清单
plugins/<slug>/                          # 每个均有 pyproject、plugin.json、lock、src、tests
migration-adapters/src/ailove_migration/ # 当前重构临时包装，最终删除
deployment/manifests/                    # 当前插件/实例/绑定，非版本目录
deployment/local/                       # 本地隔离集成环境配置
scripts/plugins/                        # 构建、产物验证、场景验收 PowerShell 入口
tests/plugin_contracts/                  # 当前契约、公开控制面
tests/plugin_integration/                # 正式实例和真实业务链
tests/plugin_recovery/                   # 排空、崩溃、数据交接
tests/plugin_architecture/               # 直接/传递依赖和产物检查
admin/console/backend/                   # 现有登录与插件控制代理
admin/console/frontend/                  # 通用插件表单、状态、历史诊断
deploy/                                 # 保留现有 Compose/K8s，修改文件不发布
```

**Structure Decision**: 将 architecture.md 的各宿主目录收敛为一个 `hosts/runtime` 包，通过 role 和清单组合能力，保持既有服务名称和部署职责；不创建八套重复启动框架。核心依赖 contracts，platform 和 host 依赖 core/contracts，业务插件只依赖 contracts 与自己的库。`hosts/runtime` 不能 import 具体插件，也不能把旧服务类直接搬进核心；初始化、资源借用与业务逻辑先分别归位。控制台暂留原路径避免无关移动。

每个插件入口固定在 `plugins/<slug>/src/ailove_plugin_<slug_with_underscores>/plugin.py`；元数据为 `plugins/<slug>/plugin.json`。表中同一行列举多个 slug 时，每个独立打包/依赖/验收，不能只发布整行合并包。

| 包 slug（共 31） | 当前来源/职责 | 宿主及模式 |
|---|---|---|
| channel-qq | gateway/qq_channel.py、QQ 同步/联系人/QZone 协议适配 | gateway worker；核心保留账号路由和发送账本 |
| content-quote, content-forward, content-voice, content-image, content-file, content-at, content-text | gateway/content_type_resolver.py 七种 entry points | gateway trusted-inprocess；纯规范化能力可被 channel worker 通过代理调用 |
| conversation-langchain | agent/conversation/chat_agent.py、failover_chat_agent.py 的可变生成编排 | ai-agent worker；不导出 LangChain 对象 |
| model-openai, model-anthropic, model-deepseek | shared/chat_model_strategy.py 和 factory 的供应商部分 | 现有消费宿主按需 worker |
| media-vision | agent/vision；资源获取和视觉解释 | ai-agent worker |
| speech-gptsovits-client, speech-gptsovits-engine, speech-mimo-engine | agent/speech、gptsovits | ai-agent / gptsovits worker |
| memory-default, relationship-default, sticker-default | memory 包；先整体包装后拆所有权 | ai-agent trusted-inprocess |
| social-proactive, social-group-participation, social-group-repeat, social-qzone | agent/social 可替换决策；私聊任务持久协调留核心 | ai-agent trusted-inprocess，调度受 Scope 管理 |
| tool-grounding, tool-weather, tool-music, tool-web-search | extensions/host、extensions/mcp | extension-host worker；单 MCP 服务只代理目录 |
| tool-mcp-bridge | extensions/host/mcp_tool_provider.py 的远端 MCP 客户端方向 | extension-host worker；不同于通用 MCP 服务端宿主 |
| live-director-default, live-avatar-default, live-stream-default | live/director、live/avatar、live/stream | director/live-edge trusted-inprocess；保留当前占位实现边界 |

插件 UI 由所属包声明，不另加任意 JS 插件体系。人物配置/固定身份和私聊领取/发送一致性不是可替换插件策略。QZone 协议在 channel-qq，关系决策在 social-qzone；二者只通过能力契约连接。

## Implementation Decisions

### 运行控制与最小启动

每个宿主有管理器，部署 role 只提供资源配置和清单路径。控制台通过平台 RPC 转发至目标宿主；管理 CLI 使用同一应用层服务。持久 OperationStore 位于 PostgreSQL；零业务插件仍可启动控制面。基础设施不可用时仍提供 liveness 与只读诊断，变更入口拒绝而不降级成无持久日志的执行。

提供单一当前契约与 `ai_love.plugins` entry point；发现读取外置 JSON，不执行 import。实例身份、作用域、资源账本、绑定和活动代次与具体实现分离。worker 用双向 length-prefixed JSON over stdio，stdout 仅协议、stderr 日志；宿主代理限定能力和资源。详细协议见 contracts/lifecycle.md。

### 并发、停止与持久状态

PostgreSQL 事务内写操作阶段和活动绑定，用行锁与期望修订防止并发提交。既有私聊领取锁順序“联系人→任务→发送”保持；管理器切换锁不跨外部 I/O 长持有，使用短事务和持久阶段记录。内存路由副本最终同步，写入边界按权威代次拒绝旧实例。

数据库和 NATS KV 不声称分布式原子提交。Memory 切换先禁止新扫描、排空、停止所有旧写入，再记录数据库与 KV 联合水位；无法确认旧写入结束时阻断接管并受控重启宿主。正常切换不重置既有 durable 名、领取代次和幂等键。对发送成功但确认未知，不进行自动重放。

每个插件只拿 ScopedStore/EventPort/ActionPort 等授权代理，不拿 Database、全局 Nacos、bus 或宿主对象。平台实现继续复用现有仓储语义，按数据所有权逐步迁移 ORM 位置；插件私有 migration 与核心迁移分开登记，现有 Alembic 历史不改写。

### 独立交付与迁移顺序

普通 worker 每实例/插件有独立环境；可信进程内插件代码替换使用受控宿主重启。不允许插件安装修改核心环境锁；进程内依赖与宿主冲突则报告无法装载，不偷偷联动升级。强隔离模式使用最小权限容器、禁止宿主凭据继承、网络/卷白名单；不满足隔离需求就拒绝。

迁移按 architecture.md 第 6 节：基线→契约/管理→语音/工具切片→模型/视觉→QQ→Memory/社交→直播/控制台→移除迁移适配层。任务按 US1～US5 分组：US1 做最小正常路径，US2/3/4 完善替换/故障/授权，US5 完成全部内置插件迁移；不能将 US1 的切片通过宣称为所有插件完成。

## Verification and Delivery

- FR-023 和 acceptance.md 明确要求测试，任务采用先契约/入口测试再实现；轻量文档或机械移动无需镜像实现的细碎测试。
- 输出目录 `output/plugin-architecture/` 记录环境、产物摘要、31 包清单、测试边界、控制组与迁移组指标。功能门槛见 SC-001～008，40 项验收按实际插件逐一记录。
- 本地验证使用 `deployment/local/compose.plugins.yml`，独立项目/数据卷和环回端口；不继承生产 Nacos/数据库 URL。不使用当前 deploy 的默认启动命令作为测试环境。
- 外部平台/模型的实际连通性由后续明确授权环境验证；当前计划与任务不包含部署、推送或 Nacos 写入动作。生成性的测试使用固定响应和明确定义场景，不比较自然语言逐字一致。
- MVP 是 US1 完整切片（先选 speech-gptsovits-client）通过零插件、安装、正常业务、停用、物理移除；整体交付必须覆盖全部用户故事、31 个包和最终门槛。

## Complexity Tracking

无未解决的宪章违规。新增三个边界包、一个通用宿主及按需 worker 各有独立依赖/卸载的实际收益；无新增默认微服务、插件版本体系或任意通用扩展钩子。尚未实测的延迟/恢复指标是实施验收目标，不是设计检查已经证明的运行结果。

## Planning validation — 2026-09-16

- `setup-plan.ps1`、`setup-tasks.ps1` 和 `check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks` 均成功，实际 Git 分支仍为 main。
- 112 项任务编号连续，故事标签/文件路径完整，全部保持未执行；30 项标有受前置依赖约束的 `[P]`。
- 31 个实际插件均有独立迁移任务；25 项 FR 均映射到任务和验收，无未决占位项或坏文档链接。
- 使用本地 jsonschema 检查清单 schema、架构示例及禁止版本字段的负例，全部通过。
- `.specify/extensions.yml` 不存在，规划/任务的前后 hooks 均按技能规则跳过；未产生外部写入。
- 上述仅为设计/任务结构验证；业务实现、产物安装、浏览器、负载及恢复验收均尚未运行。
