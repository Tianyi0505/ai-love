# Tasks: 可独立演进的插件架构

**Created**: 2026-09-16
**Input**: `specs/002-plugin-architecture/` 的 spec.md、plan.md、research.md、data-model.md、contracts/、quickstart.md。
**Prerequisites**: 设计检查已完成；本清单全部未执行。用户排除插件版本管理与兼容性机制，任何任务不得重新引入。
**Tests**: FR-023、SC-001～008 和 acceptance.md 明确要求测试。先写当前契约/正式入口测试，再实现；失败证据应为预期功能未实现，不把环境错误当有效红灯。
**Organization**: Setup → Foundation → US1～US5（P1 在前）→ 最终验收；先完成一个可独立交付切片，再扩展全部 31 插件。

## Format: `[ID] [P?] [Story] Description`

- `[P]` 仅表示下文指定同一批次中可并行的不同文件任务；前置阶段与依赖全部满足后才可并行。
- 路径相对仓库根；本计划新路径尚待创建。插件源包路径按 plan.md 规则，所有包都需自己的 pyproject.toml、plugin.json、lock、schemas、tests，不能只迁 plugin.py。
- 不覆盖原有未提交修改；测试仅本地隔离环境；没有部署、git push、Issue/PR、生产 Nacos/K8s 写入任务。
- 完成一个任务后在本文件标 `[X]` 并记录证据；不得代勾 `checklists/` 的需求质量项。acceptance.md 仅按真实执行结果记录，不因任务完成自动全勾。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 确立真实工作区基线、独立产物和可重复的本地验证环境。

- [ ] T001 记录当前工作区改动、真实入口、依赖/机器基线及现有测试模拟边界到 `output/plugin-architecture/baseline.md`，以 `tests/private_reply_fixtures.py` 和 `tests/test_private_reply_load.py` 为核查依据，禁止清理用户改动。
- [ ] T002 创建独立包与通用宿主构建配置 `packages/contracts/pyproject.toml`、`packages/core/pyproject.toml`、`packages/platform-runtime/pyproject.toml`、`hosts/runtime/pyproject.toml`，拆出供应商依赖，包构建元数据不进入插件管理逻辑。
- [ ] T003 实现 `deployment/local/compose.plugins.yml`、`scripts/plugins/prepare-local.ps1` 和 `tests/plugin_integration/conftest.py`，只生成环回 PostgreSQL/NATS/Redis/Nacos/模拟平台环境、独立测试库及受限凭据，拒绝生产连接。
- [ ] T004 实现 `scripts/plugins/build-artifacts.ps1`，独立构建/收集代码与清单资源、依赖 wheelhouse、SHA-256、环境信息到 `output/plugin-architecture/artifacts/`，不安装到核心运行环境。
- [ ] T005 检查并仅补充 `.gitignore`、`.dockerignore` 的新构建/测试输出及秘密文件忽略规则，保留当前未提交规则，不排除必须打包的插件声明/schema。
- [ ] T006 建立 `deployment/manifests/plugin-catalog.json` 的 31 包交付清单及依赖/宿主范围，未实现条目标为 pending，禁止用目录存在代替交付完成；建立 `output/plugin-architecture/results.json` 结果结构。

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有故事共享的当前契约、资源、身份与持久操作基础；该阶段不部署业务。

- [ ] T007 先在 `tests/plugin_contracts/test_manifest.py` 和 `tests/plugin_contracts/test_context.py` 定义清单/schema、作用域、禁止版本字段、禁止 SDK/ORM 穿越边界的契约测试。
- [ ] T008 在 `packages/contracts/src/ailove_contracts/lifecycle.py`、`context.py`、`errors.py` 实现生命周期 DTO、可信上下文、错误和结果语义，并将 `specs/002-plugin-architecture/contracts/plugin.schema.json` 纳入 SDK 资源。
- [ ] T009 从 `shared/contracts/` 抽取稳定事实 DTO 到 `packages/contracts/src/ailove_contracts/capabilities.py`、`events.py`，落实 `contracts/capabilities.md` 当前输入/输出和端口；保持独立 SDK 无实现 import。
- [ ] T010 在 `tests/plugin_integration/test_operation_store.py` 先定义真实 PostgreSQL 操作幂等、请求摘要冲突、绑定条件提交和锁顺序测试，不用内存 store 替代事务行为。
- [ ] T011 实现 `packages/platform-runtime/src/ailove_platform/persistence/plugin_models.py`、`operation_store.py` 和 `packages/platform-runtime/migrations/` 控制表迁移；从实施时 Alembic 实际 head 追加，不修改已有 revision。
- [ ] T012 在 `packages/core/src/ailove_core/plugins/scope.py` 实现资源拥有/借用账本、任务与作业登记、关闭顺序和残留报告，拒绝插件关闭共享宿主资源。
- [ ] T013 在 `packages/core/src/ailove_core/plugins/registry.py` 实现能力名绑定、作用域、显式顺序、唯一候选和可撤销句柄，不根据具体插件名分支。
- [ ] T014 在 `packages/core/src/ailove_core/permissions/context.py`、`gate.py` 实现默认拒绝、可信人物/账号/受众上下文和基本动作许可，候选实例激活前没有写入许可。
- [ ] T015 在 `packages/platform-runtime/src/ailove_platform/config/snapshots.py` 实现配置快照与 Nacos 默认/控制库 override 的单一 reconcile 来源，保留配置修订而非插件版本。
- [ ] T016 在 `hosts/runtime/src/ailove_host/bootstrap.py`、`health.py` 实现通用 role 启动、平台端口注入、零业务插件诊断和持久控制面失败时拒绝变更。
- [ ] T017 在 `tests/plugin_contracts/test_worker_protocol.py` 先定义双向长度帧、嵌套端口调用、取消、流序号、畸形/超限帧和身份不可伪造测试。
- [ ] T018 实现 `packages/platform-runtime/src/ailove_platform/workers/protocol.py`、`process.py` 和 `hosts/runtime/src/ailove_host/worker.py` 的受管 stdio IPC、限定环境、进程树清理和资源代理，不使用 pickle 或 shell 拼接。
- [ ] T019 在 `packages/core/src/ailove_core/plugins/discovery.py`、`loader.py` 实现无 import 发现、路径/摘要核验、trusted-inprocess 与 worker loader，进程内代码变化报告 host-restart，不实现 reload 假卸载。
- [ ] T020 运行基础契约/真实控制表/双向 worker 测试并将结果记入 `output/plugin-architecture/foundation.md`，验证平台层和宿主也无具体业务插件 import；修复失败后进入 US1。

**Checkpoint**: 当前 SDK、可撤销能力、基本授权及持久控制路径可用；全故事共用这套机制。

## Phase 3: User Story 1 - 增删插件不改核心 (Priority: P1) — MVP

**Goal**: 固定核心产物，通过正式管理入口完成一个真实插件的安装、启用、业务调用、停用和移除。
**Independent Test**: 选择 speech-gptsovits-client；用本地模拟合成 HTTP 边界，零插件宿主、安装包业务调用、卸载后重启均通过，核心/无关产物摘要不变。

### Tests first

- [ ] T021 [P] [US1] 在 `tests/plugin_contracts/test_management.py` 定义登录鉴权、preflight/install/enable/disable/remove、202 操作查询与幂等请求的正式 HTTP 契约测试。
- [ ] T022 [P] [US1] 在 `tests/plugin_integration/test_installed_speech.py` 定义仓库外 cwd、无源码挂载的 speech 客户端安装调用及物理移除场景，使用真实宿主/worker 和模拟外部语音服务。

### Implementation

- [ ] T023 [US1] 在 `packages/core/src/ailove_core/plugins/manager.py` 实现正常生命周期编排、持久操作状态、激活闸门和无必需能力时相关业务暂停，错误按当前契约返回。
- [ ] T024 [US1] 在 `hosts/runtime/src/ailove_host/management.py` 实现 `contracts/management.md` 的查询、预检和实例操作 HTTP 入口，复用当前应用层/鉴权，不绕过操作日志。
- [ ] T025 [US1] 在 `hosts/runtime/src/ailove_host/cli.py` 实现同一控制 API 的 list/status/preflight/apply/operations 客户端及受限凭据文件读取，不新增直接数据库/Nacos 管理路径。
- [ ] T026 [US1] 将 `agent/speech/gpt_sovits_provider.py` 迁入 `plugins/speech-gptsovits-client/src/ailove_plugin_speech_gptsovits_client/plugin.py`，提供独立清单/依赖和 synthesize 契约，资源由 Scope 管理。
- [ ] T027 [US1] 在 `hosts/runtime/src/ailove_host/roles.py` 和 `deployment/manifests/speech-smoke.json` 以清单配置语音测试宿主，通过当前能力调用插件；host 只认 role/契约而不 import 该插件。
- [ ] T028 [US1] 在 `admin/console/backend/plugins/router.py` 和 `admin/console/backend/app.py` 接入已鉴权管理代理，零业务插件时登录、实例列表、诊断可用。
- [ ] T029 [US1] 实现 `scripts/plugins/test-installed-artifacts.ps1`，离线安装 wheelhouse 到隔离目录并从仓库外运行 T022，核验包来源、传递依赖与卸载后的资源/文件状态。
- [ ] T030 [US1] 更新 `deployment/manifests/plugin-catalog.json` 中该实际插件的入口、安装位置和验收驱动，并生成 `tests/plugin_integration/fixtures/speech_requests.json` 的管理/业务样例。
- [ ] T031 [US1] 执行 T021/T022 和独立产物脚本，把零插件/添加/启停/移除证据写入 `output/plugin-architecture/us1.md`；只宣布该 MVP 切片完成，不宣布全部插件已迁移。

## Phase 4: User Story 2 - 替换升级后身份与状态连续 (Priority: P1)

**Goal**: 用遵循当前契约的候选实现切换业务，保留归属、持久状态和未知动作结果。
**Independent Test**: 在已安装 speech 实例及独立状态验收插件上，从公开管理入口替换、导入失败、切换中退出、恢复；不依赖 US5 全量迁移。

### Tests first

- [ ] T032 [P] [US2] 在 `tests/plugin_recovery/test_replace.py` 定义同插件新产物及不同插件同能力替换的正式入口场景，覆盖在途请求与 host-restart 模式。
- [ ] T033 [P] [US2] 在 `tests/plugin_recovery/test_state_handoff.py` 定义本地数据库/KV 联合静止点、导入失败、候选无写权限和未知发送恢复场景，使用真实本地持久设施。

### Implementation

- [ ] T034 [US2] 在 `packages/core/src/ailove_core/plugins/replacement.py` 实现 prepare/quiesce/commit/cleanup 与有状态单写者交接、代次条件提交，管理器调用新组件而不加入版本选择。
- [ ] T035 [US2] 在 `packages/core/src/ailove_core/plugins/state_transfer.py` 和 `packages/platform-runtime/src/ailove_platform/persistence/handoff.py` 实现限定 owner 的快照/校验/水位记录及本次恢复步骤，禁止插件读其他私有表。
- [ ] T036 [US2] 在 `packages/core/src/ailove_core/turns/action_gateway.py` 实现动作代次、授权、幂等键和不可变摘要校验；候选不能执行副作用，旧实例在切换后不能继续写入。
- [ ] T037 [US2] 从 `shared/private_interaction_repository.py`、`shared/social_delivery_repository.py` 抽取平台实现到 `packages/platform-runtime/src/ailove_platform/persistence/private_jobs.py`、`deliveries.py`，保留锁顺序、claim_version 领取语义及 unknown，不改数据 ID。
- [ ] T038 [US2] 创建正式可安装的同能力/状态验收包 `tests/plugin_integration/fixtures/plugins/state_probe/pyproject.toml` 与 speech 替代者 `tests/plugin_integration/fixtures/plugins/speech_alternative/pyproject.toml`，标明仅用于机制测试、不能替代内置插件验收。
- [ ] T039 [US2] 在 `packages/core/src/ailove_core/operations/recovery.py` 实现切换提交前补偿与提交后按操作日志恢复；状态未知时阻断接管，不自动重发已提交/未知动作。
- [ ] T040 [US2] 经公开管理/业务入口执行替换与状态测试并写入 `output/plugin-architecture/us2.md`，核对核心及无关产物摘要不变、数据归属和操作结果真实。

## Phase 5: User Story 3 - 生命周期可控且故障可定位 (Priority: P1)

**Goal**: 有界停止、完整资源回收、并发变更控制、宿主恢复与诊断覆盖后台工作。
**Independent Test**: 使用 US1 实际插件及故障验收包，逐阶段故障、管理请求竞争、进程退出和 100 次启停，无关能力作为控制组。

### Tests first

- [ ] T041 [P] [US3] 在 `tests/plugin_recovery/test_lifecycle_failures.py` 定义每阶段部分失败、停止超时、资源残留和重复 operation_id 场景；故障通过测试插件声明注入，不手改核心内部状态。
- [ ] T042 [P] [US3] 在 `tests/plugin_recovery/test_host_restart.py` 定义双管理请求、双副本 CAS、各切换阶段宿主退出、旧 worker 重连和恢复场景。

### Implementation

- [ ] T043 [US3] 在 `packages/core/src/ailove_core/plugins/drain.py` 扩展 Scope 的入口闸门、前后台活动计数、30 秒控制/60 秒排空预算、超时报告及受控恢复路径。
- [ ] T044 [US3] 在 `packages/platform-runtime/src/ailove_platform/nats/subscriptions.py`、`scheduler.py` 实现等待底层取消/排空的订阅句柄和按实例调度作业，不以只 cancel pump 代替清理完成。
- [ ] T045 [US3] 在 `packages/core/src/ailove_core/plugins/resilience.py` 实现 deadline 贯穿、最多两次只读重试、实例并发/积压上限、熔断与显式 overloaded，不重试未知动作。
- [ ] T046 [US3] 完善 `packages/core/src/ailove_core/operations/reconciler.py` 的持久阶段重入、依赖锁顺序和旧代次封禁，接管前确认旧写入者静止。
- [ ] T047 [US3] 在 `packages/core/src/ailove_core/operations/telemetry.py` 接入实例/代次/操作/修订/事件日志和指标，记录残留、最老积压、恢复水位与失败指引，禁止敏感正文。
- [ ] T048 [US3] 在 `hosts/runtime/src/ailove_host/shutdown.py` 和 `__main__.py` 统一异常/信号 finally 停止，Windows 与 Linux 均覆盖资源退出与进程树回收。
- [ ] T049 [US3] 完善 `hosts/runtime/src/ailove_host/health.py` 区分 liveness、管理就绪和逐能力 readiness，持久控制面故障时保持诊断但拒绝变更。
- [ ] T050 [US3] 实现 `scripts/plugins/test-conformance.ps1` 的 Catalog/Plugin/All/Cycles 参数、管理入口驱动、控制组流量与 100 次资源基线比较，并在 `tests/plugin_integration/fixtures/plugins/capability_alternatives/` 为各当前能力提供可安装的替代验收实现；为实际包保留未验收状态，替身不能代替被测插件。
- [ ] T051 [US3] 执行生命周期/竞争/重启和循环检查，写入 `output/plugin-architecture/us3.md`；有残留、假成功或控制组失败则修复后继续。

## Phase 6: User Story 4 - 配置、授权和能力依赖独立管理 (Priority: P1)

**Goal**: 配置覆盖、授权撤销、依赖解析、强隔离与声明式 UI 独立于具体插件。
**Independent Test**: 已安装实例上无效/乱序配置保留当前快照；跨 AI/账号请求和未授权网络/文件拒绝；UI 无重新构建即可添加/撤销贡献。

### Tests first

- [ ] T052 [P] [US4] 在 `tests/plugin_contracts/test_configuration.py` 定义配置/依赖失败测试，并在 `admin/console/frontend/tests/plugins.spec.ts` 先定义贡献增删、鉴权及旧页面撤销场景；通过 `admin/console/frontend/playwright.config.ts`、`package.json` 配置浏览器测试依赖和 test:plugins 入口，先取得预期失败。
- [ ] T053 [P] [US4] 在 `tests/plugin_integration/test_permissions_isolation.py` 定义实际作用域/撤销/永久禁用/conditional/confirm、worker 资源访问和不具备隔离时拒绝激活场景。

### Implementation

- [ ] T054 [US4] 在 `packages/core/src/ailove_core/plugins/configuration.py` 实现当前 schema 验证、配置事务、热改声明及替换触发，并对接 T015 的 Nacos/override 单一 reconcile。
- [ ] T055 [US4] 在 `packages/platform-runtime/src/ailove_platform/scoped_ports.py` 实现受限网络、目录、状态、事件与共享会话端口，禁止裸 DB/bus/Nacos/host/全量环境进入 PluginContext。
- [ ] T056 [US4] 在 `packages/core/src/ailove_core/permissions/grants.py` 实现授权求交、条件判定、可信确认与即时撤销；保留四类永久禁止操作且执行端复查。
- [ ] T057 [US4] 在 `packages/platform-runtime/src/ailove_platform/workers/restricted.py`、`deployment/local/restricted-worker.json` 实现受控容器最小身份、文件/网络和资源限制；Windows 缺少条件时返回 isolation_unavailable。
- [ ] T058 [US4] 在 `packages/core/src/ailove_core/plugins/contributions.py`、`admin/console/backend/plugins/contributions.py` 实现声明式贡献目录/查询/动作的范围授权、修订通知和撤销 410。
- [ ] T059 [US4] 在 `admin/console/frontend/src/features/plugins/renderer.tsx`、`page.tsx` 实现 status/form/table/document 通用渲染与操作状态，不执行任意 JS/URL。
- [ ] T060 [US4] 修改 `admin/console/frontend/src/app.tsx`、`layout/navigation.ts` 接入固定 extensions 路由及动态导航，旧页面撤销后不可继续操作；暂保留尚未迁移业务页至 US5。
- [ ] T061 [US4] 执行 T052 配置的 test:plugins 入口，完善 `admin/console/frontend/tests/plugins.spec.ts` 的后端 fixtures，固定同一前端构建验证贡献增删、鉴权、旧页面撤销；失败先修复再接入其余管理端点。
- [ ] T062 [US4] 在 `hosts/runtime/src/ailove_host/management.py`、`admin/console/backend/plugins/router.py` 完成配置/授权/贡献端点与冲突响应，绑定已定义操作记录和审计。
- [ ] T063 [US4] 执行配置/权限/隔离/浏览器验证并写 `output/plugin-architecture/us4.md`，明确本地普通 worker 与 Linux 强隔离实际覆盖的不同保证。

## Phase 7: User Story 5 - 渐进迁移现有行为 (Priority: P2)

**Goal**: 全部 31 个实际插件独立交付；旧路径逐范围退役，人物、消息、记忆和动作语义不回退。
**Independent Test**: 同一批脱敏事件/固定模型响应经旧路径和新正式宿主比较，只活动路径产生副作用；每迁一组插件先独立包及能力验证，再宿主集成。

### Tests and migration boundary first

- [ ] T064 [P] [US5] 在 `tests/plugin_integration/test_gateway_agent_flow.py`、`fixtures/napcat_server.py` 定义正式 WS/HTTP→Gateway→NATS→Agent→发送账本→平台确认的真实入口场景，覆盖私聊、群聊、引用和重连。
- [ ] T065 [P] [US5] 在 `tests/plugin_integration/test_memory_pipeline.py`、`test_business_parity.py` 定义真实 activity/调度→Episode/Atom/合并、双 AI、受众/作息与旧新固定响应对照；占位动作必须返回 unsupported。
- [ ] T066 [US5] 在 `migration-adapters/src/ailove_migration/legacy.py` 及 `deployment/manifests/migration.json` 包装现有实现并引入按 AI/账号/能力的路由开关，只有活动路径有动作许可，不支持历史插件接口；记录删除门槛。

### Speech and tools

- [ ] T067 [P] [US5] 将 GPT-SoVITS 引擎迁入 `plugins/speech-gptsovits-engine/src/ailove_plugin_speech_gptsovits_engine/plugin.py`，独立配置/依赖/语音引用及 Scope 连接，沿用现有合成行为。
- [ ] T068 [P] [US5] 将 MIMO 引擎迁入 `plugins/speech-mimo-engine/src/ailove_plugin_speech_mimo_engine/plugin.py`，实现相同当前 synthesize 契约及停止资源清理。
- [ ] T069 [P] [US5] 将 Grounding 工具迁入 `plugins/tool-grounding/src/ailove_plugin_tool_grounding/plugin.py`，仅使用可信上下文和身份/历史查询端口。
- [ ] T070 [P] [US5] 将天气工具和客户端资源迁入 `plugins/tool-weather/src/ailove_plugin_tool_weather/plugin.py`，私有配置/schema 与受限网络访问随包交付。
- [ ] T071 [P] [US5] 将音乐控制迁入 `plugins/tool-music/src/ailove_plugin_tool_music/plugin.py`，保留现有接收/记录范围，未接通播放器的动作不得报告执行成功。
- [ ] T072 [P] [US5] 将网络搜索迁入 `plugins/tool-web-search/src/ailove_plugin_tool_web_search/plugin.py`，资源/配置随包，不导入天气或音乐实现。
- [ ] T073 [P] [US5] 将 MCPToolProvider 迁入 `plugins/tool-mcp-bridge/src/ailove_plugin_tool_mcp_bridge/plugin.py`，受管发现刷新、当前工具目录和标准结果，不在宿主固定构造。
- [ ] T074 [US5] 重构 `extensions/host/extension_host_service.py`、`extensions/mcp/mcp_server.py`、`gptsovits/gpt_sovits_service.py` 为通用宿主入口与能力代理，移除集中供应商注册/资源组装，保留单 MCP 部署。

### Models and turn orchestration

- [ ] T075 [P] [US5] 从全局模型工厂迁出 OpenAI 适配到 `plugins/model-openai/src/ailove_plugin_model_openai/plugin.py`，标准消息/工具意图/usage 转换留包内。
- [ ] T076 [P] [US5] 迁移 Anthropic 到 `plugins/model-anthropic/src/ailove_plugin_model_anthropic/plugin.py`，独立锁与 worker 环境，不泄露 SDK 对象。
- [ ] T077 [P] [US5] 迁移 DeepSeek 到 `plugins/model-deepseek/src/ailove_plugin_model_deepseek/plugin.py`，保留现有模型参数语义和有限超时。
- [ ] T078 [US5] 将可变 LangChain 编排迁入 `plugins/conversation-langchain/src/ailove_plugin_conversation_langchain/plugin.py`，经 model.generate/ActionPort 代理调用，保留配置顺序故障切换和工具快照失效。
- [ ] T079 [US5] 迁移视觉获取/解释到 `plugins/media-vision/src/ailove_plugin_media_vision/plugin.py`，保留原图优先、多模态失败后带发送者来源的描述回退，不虚构语音能力。
- [ ] T080 [US5] 从 `agent/ai_runtime.py`、`agent/social/private_reply_service.py` 提取稳定协调到 `packages/core/src/ailove_core/turns/coordinator.py`、`private_reply.py`，消除 `_host._db`，保持任务/受众/顺序不变量并经能力代理调用。

### Channel and content

- [ ] T081 [P] [US5] 迁移引用策略到 `plugins/content-quote/src/ailove_plugin_content_quote/plugin.py`，独立规范化包保留引用事实和未命中语义。
- [ ] T082 [P] [US5] 迁移转发策略到 `plugins/content-forward/src/ailove_plugin_content_forward/plugin.py`，保留内联转发与来源结构。
- [ ] T083 [P] [US5] 迁移语音内容判定到 `plugins/content-voice/src/ailove_plugin_content_voice/plugin.py`，仅描述内容类型，不增加未接入 ASR。
- [ ] T084 [P] [US5] 迁移图片策略到 `plugins/content-image/src/ailove_plugin_content_image/plugin.py`，保留资源引用与 sender 归属。
- [ ] T085 [P] [US5] 迁移文件策略到 `plugins/content-file/src/ailove_plugin_content_file/plugin.py`，保持文件事实和限制。
- [ ] T086 [P] [US5] 迁移提及策略到 `plugins/content-at/src/ailove_plugin_content_at/plugin.py`，保留 mention 目标，不擅自合并身份。
- [ ] T087 [P] [US5] 迁移文本策略到 `plugins/content-text/src/ailove_plugin_content_text/plugin.py`，作为显式有序最后策略，不在核心构造默认实例。
- [ ] T088 [US5] 将 QQ 连接、协议、联系人/白名单同步和 QZone 平台适配迁入 `plugins/channel-qq/src/ailove_plugin_channel_qq/plugin.py`，通过代理消费内容策略；保留 NapCat 登录态、引用、重连和账号范围。
- [ ] T089 [US5] 重构 `gateway/gateway_service.py`、`gateway/gateway_message_handler.py`、`gateway/social_send_handler.py` 的入口与协调，移除 QQ 特定组装；群聊/QZone 动作也经 `packages/core/src/ailove_core/turns/action_gateway.py`，不假定私聊账本已覆盖。

### Stateful capabilities and social policies

- [ ] T090 [US5] 将 Memory 整体先包装再迁到 `plugins/memory-default/src/ailove_plugin_memory_default/plugin.py`，保持 ai-agent 进程内、静默/批量归并，登记全部订阅/作业并提供联合状态交接。
- [ ] T091 [US5] 从 Memory 组装中拆出关系到 `plugins/relationship-default/src/ailove_plugin_relationship_default/plugin.py`，按 AI+person 公开端口读写，调用方不依赖插件 ORM。
- [ ] T092 [US5] 拆出表情到 `plugins/sticker-default/src/ailove_plugin_sticker_default/plugin.py`，素材归属/保留与清理任务受 Scope 管理，缺失时可省略表情。
- [ ] T093 [US5] 将主动联系策略迁入 `plugins/social-proactive/src/ailove_plugin_social_proactive/plugin.py`，保持作息、联系人状态和停止条件，意图经核心动作许可。
- [ ] T094 [US5] 将群参与策略迁入 `plugins/social-group-participation/src/ailove_plugin_social_group_participation/plugin.py`，保留旁听/沉默、关系及受众判断。
- [ ] T095 [US5] 将复读策略迁入 `plugins/social-group-repeat/src/ailove_plugin_social_group_repeat/plugin.py`，通过 SessionPort 保存 AI 范围状态，模型调用预算不增加。
- [ ] T096 [US5] 将 QZone 评论/互动策略迁入 `plugins/social-qzone/src/ailove_plugin_social_qzone/plugin.py`，按人物关系决策，平台动作通过 channel 能力和核心授权，不直接访问 NapCat。
- [ ] T097 [US5] 重构 `agent/ai_agent_service.py`、`agent/agent_supervisor.py`、`agent/extension_toolset_loader.py` 的组装与工具快照，人物 runtime 消费稳定能力，Memory 独立停用不关闭其他实例资源。

### Live and administration

- [ ] T098 [P] [US5] 将导演策略迁入 `plugins/live-director-default/src/ailove_plugin_live_director_default/plugin.py`，保留场次范围和事件分配。
- [ ] T099 [P] [US5] 将 Avatar 事件处理迁入 `plugins/live-avatar-default/src/ailove_plugin_live_avatar_default/plugin.py`，迁移实际订阅/日志行为，未接通执行明确 unsupported。
- [ ] T100 [P] [US5] 将 Stream 事件处理迁入 `plugins/live-stream-default/src/ailove_plugin_live_stream_default/plugin.py`，不隐含新增 OBS 驱动，不把日志视为推流确认。
- [ ] T101 [US5] 将 `live/director/director_service.py`、`live/edge_service.py` 组装改为通用能力清单，场次/设备切换和停止覆盖全部订阅。
- [ ] T102 [US5] 修改 `admin/console/backend/observability/people_memory.py`、`self_memory.py`、`personality.py` 及前端 `features/memory/people_page.tsx`、`self_page.tsx`、`features/personality/page.tsx`，迁移到公开查询/声明式贡献，移除 app/router 对具体 reader 和页面的静态绑定。
- [ ] T103 [US5] 执行完整 Gateway/Agent/Memory/MCP/直播/控制台入口与旧新对照测试，记录每包公开入口、外部模拟及当前占位能力到 `output/plugin-architecture/us5.md`，修复归属、时序或模型调用回退。
- [ ] T104 [US5] 完成 `deployment/manifests/plugin-catalog.json` 的全部包/能力/宿主映射，并在 `docs/plugin-migration.md` 定义每个旧包装器退出条件、配置转换、维护窗口及状态恢复步骤，禁止自动发布外部配置。

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 删除旧路径、验独立产物、完成负载/恢复与全插件六项门槛；不是新增功能阶段。

- [ ] T105 运行并完善 `scripts/plugins/build-artifacts.ps1`，为 31 包填齐元数据、资源和独立锁；无源码挂载安装验证实际代码和声明均来自 wheel，更新 `output/plugin-architecture/artifacts/index.json`。
- [ ] T106 修改 `deploy/Dockerfile`、`deploy/docker-compose.yml`、`deploy/docker-compose.local.yml`、`deploy/docker-compose.cloud.yml`、`deploy/k8s/apps.yaml` 和 `deploy/nacos/service.gateway.yaml`、`service.ai-agent.yaml`、`service.extension-host.yaml`、`service.gptsovits.yaml`、`service.director.yaml`、`service.live-edge.yaml`（均在 deploy/nacos/），使核心镜像与插件产物分开交付，保持服务职责及 NapCat 配置；只编辑不部署。
- [ ] T107 在所有退出门槛满足后移除 `migration-adapters/`，清理 `pyproject.toml` 的集中具体 entry points、`requirements.txt` 的联合供应商依赖和 `shared/chat_model_strategy.py` 的全局注册；停止依赖整仓 COPY，保留用户数据和既有迁移历史。
- [ ] T108 在 `tests/plugin_architecture/test_boundaries.py`、`test_artifacts.py` 完成直接/传递依赖、宿主具体分支、配置/路由静态绑定及无版本管理检查，重新执行物理移除与零插件启动。
- [ ] T109 实现并运行 `scripts/plugins/test-recovery.ps1`，从公开操作入口覆盖各阶段故障、数据库/KV/consumer 联合恢复、旧代次拒绝、unknown 发送，输出实际恢复时间和已确认状态对账。
- [ ] T110 实现并运行 `scripts/plugins/test-load.ps1` 的 Persons/Conversations/EventsPerSecond/DurationSeconds/OutputDirectory 参数，按 SC-006 测真实本地入口、固定响应对照，报告 P95/错误/调用/token，不能沿用旧低负载阈值冒充。
- [ ] T111 对 `deployment/manifests/plugin-catalog.json` 全 31 包运行六项独立变更与 100 次启停，并执行 `admin/console/frontend/package.json` 的构建/浏览器验证；逐项填写 `specs/002-plugin-architecture/acceptance.md` 适用项证据，不把模拟说成生产验证。
- [ ] T112 更新 `README.md`、`docs/plugin-authoring.md`、`docs/plugin-operations.md` 和 `specs/002-plugin-architecture/quickstart.md` 的真实命令及限制，在 `output/plugin-architecture/final-report.md` 汇总 SC-001～008 与全部 FR 验收；任何未通过项保留未完成状态。

## Dependencies & Execution Order

### Phase dependencies

```text
Setup T001–T006
  → Foundation T007–T020
    → US1 T021–T031
      → US2 T032–T040
        → US3 T041–T051
          → US4 T052–T063
            → US5 T064–T104
              → Polish T105–T112
```

默认按此顺序执行，同优先级也服从真实依赖。每个故事有自己的完整公开入口场景，但并不意味着它们无需共享基础或可无条件同时开发。US2/US3 的状态/故障验收包可在 US5 完成前验证机制；最后仍由 T111 对全部实际插件复验。

### Explicit dependencies within phases

- Foundation：T007→T008→T009；T010→T011；T012～T016 依赖前述契约/持久结构；T017→T018→T019；T020 汇总全部。
- US1：T021/T022 先于 T023；T024/T025/T028 依赖 T023；T026/T027 依赖 loader 与契约；T029/T030 后执行 T031。
- US2：T032/T033→T034/T035；T036/T037 提供写入许可与账本；T038 是场景所需包；全部实现后 T039/T040 验证恢复。
- US3：T041/T042 在故障逻辑前；T043/T044→T045/T046→T047/T048/T049→T050/T051。同一 manager/scope/host 文件的修改按顺序合并。
- US4：T052/T053→T054～T057；T058→T059→T060→T061；T062 在应用层完成后接线，T063 收束。普通 worker 与强隔离的证据不可互相替代。
- US5：T064/T065→T066；T067/T068 与 T069～T073 的各批次完成后 T074；T075～T077→T078/T079→T080；T081～T087→T088→T089；T090→T091→T092→T093～T096→T097；T098～T100→T101；T102→T103→T104。
- 收尾：T105/T106 成功且全部旧路径退出条件满足后才 T107；T108～T111 必须在移除旧路径后复验，T112 不得把失败或未运行项目改成完成。

### Parallel execution examples

以下各组仅在其前置完成后并行，组间仍按上述顺序；没有标 `[P]` 的共享文件任务保持串行。

| 故事 | 可并行批次 | 原因 |
|---|---|---|
| US1 | T021、T022 | 管理契约与安装业务入口测试文件独立 |
| US2 | T032、T033 | 替换与状态交接测试独立 |
| US3 | T041、T042 | 阶段故障与宿主重启测试独立 |
| US4 | T052、T053 | 配置与权限/隔离测试独立 |
| US5 | T064、T065；T067、T068；T069～T073；T075～T077；T081～T087；T098～T100 | 各批分别写不同测试文件/插件包；宿主接线与原源码清理另行串行 |

## Requirement and acceptance coverage

| 需求 | 主要任务 | 验收 |
|---|---|---|
| FR-001/002/003/023 | T002/004/019/021～031/105/107/108/111 | ACC-001～006/040；SC-001/002 |
| FR-004/005/006/014 | T007～009/013/015/019/030/052/054/104/108 | ACC-007～012；无插件版本及兼容机制 |
| FR-007/008/009 | T010～012/023/034/039/041～051 | ACC-013～019；SC-003/004/007 |
| FR-010/011/012/024 | T032～040/065/080/089～092/109 | ACC-020～026；SC-005/007/008 |
| FR-013/015/016/017 | T014/015/018/052～057/062/063 | ACC-027～030/032 |
| FR-018/019 | T036/039/043～049/055/074/089/097/109/110 | ACC-017/022/023/031/032；SC-003/006/007 |
| FR-020/025 | T021/024/025/028/058～063/102/111 | ACC-027/038；鉴权、预检、异步操作及撤销 |
| FR-021/022 | T001/064～104/106/107/111/112 | ACC-033～040；SC-005/006 |

31 包的直接迁移任务：speech 客户端 T026；两引擎 T067/T068；五工具 T069～T073；三模型 T075～T077；conversation/media T078/T079；七内容 T081～T087；QQ T088；三状态 T090～T092；四社交 T093～T096；三直播 T098～T100。每项完成必须包含独立包及对应入口测试，T111 最终复验不能缺任何一项。

## Implementation Strategy

1. 先完成 T001～T031 得到 US1 MVP；只证明一个真实插件完整可插拔，不省略最终范围。
2. 完成 US2/3/4，验证持久交接、失败清理和授权，再迁移有状态业务；不在候选实例上执行影子副作用。
3. US5 按能力逐范围切换，回归失败先恢复/修复本组；不推进到会掩盖问题的新组。临时包装器的用途仅为本次 Strangler 迁移。
4. 全部实际包通过后删除旧路径，重新跑产物/恢复/负载/前端和全插件矩阵。完成报告必须列未验证外部环境与占位业务能力。

## Task summary

112 项：Setup 6，Foundation 14，US1 11，US2 9，US3 11，US4 12，US5 41，Polish 8。所有任务未执行；阶段完成条件是实际证据通过，而非本文件生成。任务格式统一为 checkbox + 顺序 ID + 故事标签（故事阶段）+ 文件路径。
