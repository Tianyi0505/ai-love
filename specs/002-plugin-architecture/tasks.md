# Tasks: 独立插件目标结果清单

**Created**: 2026-09-16
**状态**：112 项目标结果，原有任务编号、标签、路径与勾选状态保留。
**依据**：[spec.md](spec.md)、[plan.md](plan.md)、[acceptance.md](acceptance.md)。
**标记**：`[ ]` 表示目标结果，`[x]` 表示具有实现及验收证据的完成结果。

## Phase 1: 基础资料

- [ ] T001 基线资料包含工作区归属、真实入口、依赖、机器与模拟范围。 路径：`output/plugin-architecture/baseline.md`、`tests/private_reply_fixtures.py`、`tests/test_private_reply_load.py`。
- [ ] T002 独立 contracts/core/platform/host 包具有固定构建边界。 路径：`packages/contracts/pyproject.toml`、`packages/core/pyproject.toml`、`packages/platform-runtime/pyproject.toml`、`hosts/runtime/pyproject.toml`。
- [ ] T003 本地环境提供环回服务、专用数据库及受限凭据。 路径：`deployment/local/compose.plugins.yml`、`scripts/plugins/prepare-local.ps1`、`tests/plugin_integration/conftest.py`。
- [ ] T004 构建产物包含代码、清单、schema、wheelhouse 与摘要。 路径：`scripts/plugins/build-artifacts.ps1`、`output/plugin-architecture/artifacts/`。
- [ ] T005 忽略规则准确覆盖构建输出和私有资料，交付资源保持可见。 路径：`.gitignore`、`.dockerignore`。
- [ ] T006 31 包清单和结果结构准确表达交付范围。 路径：`deployment/manifests/plugin-catalog.json`、`output/plugin-architecture/results.json`。
## Phase 2: 共同能力

- [ ] T007 清单和上下文契约具有公开字段及可信 scope 验收标准。 路径：`tests/plugin_contracts/test_manifest.py`、`tests/plugin_contracts/test_context.py`。
- [ ] T008 生命周期、上下文与状态码采用独立 SDK 值对象。 路径：`packages/contracts/src/ailove_contracts/lifecycle.py`、`context.py`、`errors.py`、`specs/002-plugin-architecture/contracts/plugin.schema.json`。
- [ ] T009 能力与事件 DTO 具有稳定事实语义和公开端口。 路径：`shared/contracts/`、`packages/contracts/src/ailove_contracts/capabilities.py`、`events.py`、`contracts/capabilities.md`。
- [ ] T010 真实 PostgreSQL 证据覆盖操作幂等、摘要与条件提交。 路径：`tests/plugin_integration/test_operation_store.py`。
- [ ] T011 控制表及追加迁移具有实例、绑定和操作持久结构。 路径：`packages/platform-runtime/src/ailove_platform/persistence/plugin_models.py`、`operation_store.py`、`packages/platform-runtime/migrations/`。
- [ ] T012 ResourceScope 提供拥有/借用账本、资源终态及残留报告。 路径：`packages/core/src/ailove_core/plugins/scope.py`。
- [ ] T013 注册表提供显式能力绑定、顺序和可撤销句柄。 路径：`packages/core/src/ailove_core/plugins/registry.py`。
- [ ] T014 可信身份及动作网关提供当前授权和激活资格。 路径：`packages/core/src/ailove_core/permissions/context.py`、`gate.py`。
- [ ] T015 配置快照以默认输入和 override 的一致结果为依据。 路径：`packages/platform-runtime/src/ailove_platform/config/snapshots.py`。
- [ ] T016 通用 role 启动提供端口、空插件诊断和准确控制资格。 路径：`hosts/runtime/src/ailove_host/bootstrap.py`、`health.py`。
- [ ] T017 双向 worker 协议具有帧、流、取消及可信身份标准。 路径：`tests/plugin_contracts/test_worker_protocol.py`。
- [ ] T018 受管 IPC 提供限定环境、进程树和资源代理结果。 路径：`packages/platform-runtime/src/ailove_platform/workers/protocol.py`、`process.py`、`hosts/runtime/src/ailove_host/worker.py`。
- [ ] T019 发现和 loader 提供元数据核验及声明的代码生效方式。 路径：`packages/core/src/ailove_core/plugins/discovery.py`、`loader.py`。
- [ ] T020 基础结果包含契约、持久控制表及 worker 的完整证据。 路径：`output/plugin-architecture/foundation.md`。
## Phase 3: User Story 1 — 独立交付

- [ ] T021 [P] [US1] 管理 HTTP 契约具有登录、预检、操作查询和幂等标准。 路径：`tests/plugin_contracts/test_management.py`。
- [ ] T022 [P] [US1] 正式 speech 安装包具有仓库外业务入口及物理回收证据。 路径：`tests/plugin_integration/test_installed_speech.py`。
- [ ] T023 [US1] 管理器提供生命周期、持久状态和活动闸门结果。 路径：`packages/core/src/ailove_core/plugins/manager.py`。
- [ ] T024 [US1] 管理入口提供统一查询、预检、操作及真实状态。 路径：`hosts/runtime/src/ailove_host/management.py`、`contracts/management.md`。
- [ ] T025 [US1] CLI 提供统一控制 API 与受限凭据文件接口。 路径：`hosts/runtime/src/ailove_host/cli.py`。
- [ ] T026 [US1] speech 客户端具有独立产物、synthesize 契约及受管资源。 路径：`agent/speech/gpt_sovits_provider.py`、`plugins/speech-gptsovits-client/src/ailove_plugin_speech_gptsovits_client/plugin.py`。
- [ ] T027 [US1] 语音测试宿主以清单、role 和公开能力确定实例。 路径：`hosts/runtime/src/ailove_host/roles.py`、`deployment/manifests/speech-smoke.json`。
- [ ] T028 [US1] 管理代理提供已鉴权的目录和空插件诊断结果。 路径：`admin/console/backend/plugins/router.py`、`admin/console/backend/app.py`。
- [ ] T029 [US1] 离线安装包证据包含来源、依赖与资源回收状态。 路径：`scripts/plugins/test-installed-artifacts.ps1`。
- [ ] T030 [US1] speech 目录及样例准确映射实际入口和独立产物。 路径：`deployment/manifests/plugin-catalog.json`、`tests/plugin_integration/fixtures/speech_requests.json`。
- [ ] T031 [US1] US1 具有空插件、添加、启停和移除的最小交付证据。 路径：`output/plugin-architecture/us1.md`。
## Phase 4: User Story 2 — 状态连续

- [ ] T032 [P] [US2] 替换证据覆盖当前契约、在途请求和声明的代码生效方式。 路径：`tests/plugin_recovery/test_replace.py`。
- [ ] T033 [P] [US2] 联合状态标准包含 DB/KV、水位、候选资格和动作凭证。 路径：`tests/plugin_recovery/test_state_handoff.py`。
- [ ] T034 [US2] 替换组件提供候选核验、单写者与原子活动代次。 路径：`packages/core/src/ailove_core/plugins/replacement.py`。
- [ ] T035 [US2] 状态交接提供 owner、快照、checksum 与联合水位。 路径：`packages/core/src/ailove_core/plugins/state_transfer.py`、`packages/platform-runtime/src/ailove_platform/persistence/handoff.py`。
- [ ] T036 [US2] 动作网关校验当前代次、授权、固定键和摘要。 路径：`packages/core/src/ailove_core/turns/action_gateway.py`。
- [ ] T037 [US2] 私聊平台仓库保留锁顺序、领取版本和 unknown 语义。 路径：`shared/private_interaction_repository.py`、`shared/social_delivery_repository.py`、`packages/platform-runtime/src/ailove_platform/persistence/private_jobs.py`、`deliveries.py`。
- [ ] T038 [US2] 正式验收包提供同能力替代者及状态探针。 路径：`tests/plugin_integration/fixtures/plugins/state_probe/pyproject.toml`、`tests/plugin_integration/fixtures/plugins/speech_alternative/pyproject.toml`。
- [ ] T039 [US2] 操作恢复提供当前持久状态、确认凭证与唯一活动实例。 路径：`packages/core/src/ailove_core/operations/recovery.py`。
- [ ] T040 [US2] US2 具有独立替换、状态归属和固定产物证据。 路径：`output/plugin-architecture/us2.md`。
## Phase 5: User Story 3 — 生命周期

- [ ] T041 [P] [US3] 各生命周期阶段具有真实状态、超时和资源结果标准。 路径：`tests/plugin_recovery/test_lifecycle_failures.py`。
- [ ] T042 [P] [US3] 宿主竞争及重启证据覆盖 CAS、代次和恢复状态。 路径：`tests/plugin_recovery/test_host_restart.py`。
- [ ] T043 [US3] Scope 排空涵盖前后台工作及 30/60 秒预算。 路径：`packages/core/src/ailove_core/plugins/drain.py`。
- [ ] T044 [US3] 订阅和作业句柄具有底层释放及实例归属结果。 路径：`packages/platform-runtime/src/ailove_platform/nats/subscriptions.py`、`scheduler.py`。
- [ ] T045 [US3] 调用预算、最多两次只读恢复及积压上限明确。 路径：`packages/core/src/ailove_core/plugins/resilience.py`。
- [ ] T046 [US3] 一致调节结果包含持久阶段、锁顺序与旧写入者静止。 路径：`packages/core/src/ailove_core/operations/reconciler.py`。
- [ ] T047 [US3] 观测资料关联实例、代次、操作、修订、事件与水位。 路径：`packages/core/src/ailove_core/operations/telemetry.py`。
- [ ] T048 [US3] 宿主退出具有统一句柄释放与进程树回收结果。 路径：`hosts/runtime/src/ailove_host/shutdown.py`、`__main__.py`。
- [ ] T049 [US3] 健康结果区分 liveness、管理就绪和逐能力 readiness。 路径：`hosts/runtime/src/ailove_host/health.py`。
- [ ] T050 [US3] 实际目录的六项变更与循环证据具有公开入口驱动。 路径：`scripts/plugins/test-conformance.ps1`、`tests/plugin_integration/fixtures/plugins/capability_alternatives/`。
- [ ] T051 [US3] US3 具有资源基线、竞争与重启的完整证据。 路径：`output/plugin-architecture/us3.md`。
## Phase 6: User Story 4 — 配置与授权

- [ ] T052 [P] [US4] 配置与 UI 契约具有覆盖、修订、鉴权和撤销标准。 路径：`tests/plugin_contracts/test_configuration.py`、`admin/console/frontend/tests/plugins.spec.ts`、`admin/console/frontend/playwright.config.ts`、`package.json`。
- [ ] T053 [P] [US4] 权限和隔离具有实际 scope、可信确认与资源范围标准。 路径：`tests/plugin_integration/test_permissions_isolation.py`。
- [ ] T054 [US4] 有效配置提供完整 schema、修订与热改资格。 路径：`packages/core/src/ailove_core/plugins/configuration.py`。
- [ ] T055 [US4] 受限端口提供网络、目录、状态、事件和会话范围。 路径：`packages/platform-runtime/src/ailove_platform/scoped_ports.py`。
- [ ] T056 [US4] 当前授权为可信策略交集，条件与确认各有有效凭证。 路径：`packages/core/src/ailove_core/permissions/grants.py`。
- [ ] T057 [US4] 强隔离环境具备最小身份、网络、文件和资源配额。 路径：`packages/platform-runtime/src/ailove_platform/workers/restricted.py`、`deployment/local/restricted-worker.json`。
- [ ] T058 [US4] 贡献目录提供实例授权、修订及 410 撤销状态。 路径：`packages/core/src/ailove_core/plugins/contributions.py`、`admin/console/backend/plugins/contributions.py`。
- [ ] T059 [US4] 通用 UI 提供 status/form/table/document 视图。 路径：`admin/console/frontend/src/features/plugins/renderer.tsx`、`page.tsx`。
- [ ] T060 [US4] 固定扩展路由和动态导航对应当前有效贡献。 路径：`admin/console/frontend/src/app.tsx`、`layout/navigation.ts`。
- [ ] T061 [US4] 同一前端构建具有贡献、鉴权和旧页面撤销证据。 路径：`admin/console/frontend/tests/plugins.spec.ts`。
- [ ] T062 [US4] 配置、授权、贡献及冲突接口对应持久操作记录。 路径：`hosts/runtime/src/ailove_host/management.py`、`admin/console/backend/plugins/router.py`。
- [ ] T063 [US4] US4 具有各模式真实配置、授权和隔离覆盖证据。 路径：`output/plugin-architecture/us4.md`。
## Phase 7: User Story 5 — 既有业务

- [ ] T064 [P] [US5] 正式平台入口标准涵盖 WS/HTTP、NATS、Agent 和发送账本。 路径：`tests/plugin_integration/test_gateway_agent_flow.py`、`fixtures/napcat_server.py`。
- [ ] T065 [P] [US5] 真实 Memory 入口标准涵盖来源、双 AI 和旧新确定性结果。 路径：`tests/plugin_integration/test_memory_pipeline.py`、`test_business_parity.py`。
- [ ] T066 [US5] 迁移边界提供显式范围与唯一动作许可。 路径：`migration-adapters/src/ailove_migration/legacy.py`、`deployment/manifests/migration.json`。
- [ ] T067 [P] [US5] GPT-SoVITS 引擎具有独立配置、依赖、声音引用及资源。 路径：`plugins/speech-gptsovits-engine/src/ailove_plugin_speech_gptsovits_engine/plugin.py`。
- [ ] T068 [P] [US5] MIMO 引擎提供同一 synthesize 契约与停止资源结果。 路径：`plugins/speech-mimo-engine/src/ailove_plugin_speech_mimo_engine/plugin.py`。
- [ ] T069 [P] [US5] Grounding 工具仅消费可信身份及公开查询端口。 路径：`plugins/tool-grounding/src/ailove_plugin_tool_grounding/plugin.py`。
- [ ] T070 [P] [US5] 天气工具提供私有 schema 与受限网络资源。 路径：`plugins/tool-weather/src/ailove_plugin_tool_weather/plugin.py`。
- [ ] T071 [P] [US5] 音乐工具交付控制指令接收与记录结果。 路径：`plugins/tool-music/src/ailove_plugin_tool_music/plugin.py`。
- [ ] T072 [P] [US5] 搜索工具具有独立资源、配置和业务输出。 路径：`plugins/tool-web-search/src/ailove_plugin_tool_web_search/plugin.py`。
- [ ] T073 [P] [US5] MCP bridge 提供受管目录刷新和标准远端结果。 路径：`plugins/tool-mcp-bridge/src/ailove_plugin_tool_mcp_bridge/plugin.py`。
- [ ] T074 [US5] 工具与语音宿主提供通用能力入口和单一 MCP 部署。 路径：`extensions/host/extension_host_service.py`、`extensions/mcp/mcp_server.py`、`gptsovits/gpt_sovits_service.py`。
- [ ] T075 [P] [US5] OpenAI 插件提供标准消息、工具意图和 usage。 路径：`plugins/model-openai/src/ailove_plugin_model_openai/plugin.py`。
- [ ] T076 [P] [US5] Anthropic 插件具有独立锁、worker 和公开值对象。 路径：`plugins/model-anthropic/src/ailove_plugin_model_anthropic/plugin.py`。
- [ ] T077 [P] [US5] DeepSeek 插件保留模型参数与有限调用预算。 路径：`plugins/model-deepseek/src/ailove_plugin_model_deepseek/plugin.py`。
- [ ] T078 [US5] LangChain 编排通过 model.generate 和 ActionPort 提供结果。 路径：`plugins/conversation-langchain/src/ailove_plugin_conversation_langchain/plugin.py`。
- [ ] T079 [US5] 视觉插件提供原图、发送者来源及图片描述结果。 路径：`plugins/media-vision/src/ailove_plugin_media_vision/plugin.py`。
- [ ] T080 [US5] 回合协调提供稳定任务、人物、受众和顺序语义。 路径：`agent/ai_runtime.py`、`agent/social/private_reply_service.py`、`packages/core/src/ailove_core/turns/coordinator.py`、`private_reply.py`。
- [ ] T081 [P] [US5] 引用插件提供独立规范化及历史事实。 路径：`plugins/content-quote/src/ailove_plugin_content_quote/plugin.py`。
- [ ] T082 [P] [US5] 转发插件保留内联结构和来源。 路径：`plugins/content-forward/src/ailove_plugin_content_forward/plugin.py`。
- [ ] T083 [P] [US5] 语音内容插件提供准确资源类型事实。 路径：`plugins/content-voice/src/ailove_plugin_content_voice/plugin.py`。
- [ ] T084 [P] [US5] 图片插件保留资源引用和发送者归属。 路径：`plugins/content-image/src/ailove_plugin_content_image/plugin.py`。
- [ ] T085 [P] [US5] 文件插件提供准确事实与资源范围。 路径：`plugins/content-file/src/ailove_plugin_content_file/plugin.py`。
- [ ] T086 [P] [US5] 提及插件保留真实目标和实体归属。 路径：`plugins/content-at/src/ailove_plugin_content_at/plugin.py`。
- [ ] T087 [P] [US5] 文本插件为显式有序内容策略。 路径：`plugins/content-text/src/ailove_plugin_content_text/plugin.py`。
- [ ] T088 [US5] QQ 插件保留连接、白名单、联系人、引用及账号范围。 路径：`plugins/channel-qq/src/ailove_plugin_channel_qq/plugin.py`。
- [ ] T089 [US5] Gateway 协调通过公开能力和动作网关提供结果。 路径：`gateway/gateway_service.py`、`gateway/gateway_message_handler.py`、`gateway/social_send_handler.py`、`packages/core/src/ailove_core/turns/action_gateway.py`。
- [ ] T090 [US5] Memory 插件保持同进程、静默归并及联合状态资料。 路径：`plugins/memory-default/src/ailove_plugin_memory_default/plugin.py`。
- [ ] T091 [US5] 关系插件提供 AI/person 范围的公开读写结果。 路径：`plugins/relationship-default/src/ailove_plugin_relationship_default/plugin.py`。
- [ ] T092 [US5] 表情插件保留素材归属、检索及资源管理。 路径：`plugins/sticker-default/src/ailove_plugin_sticker_default/plugin.py`。
- [ ] T093 [US5] 主动策略提供作息、联系状态和合法动作意图。 路径：`plugins/social-proactive/src/ailove_plugin_social_proactive/plugin.py`。
- [ ] T094 [US5] 群参与策略提供旁听、关系与受众判断。 路径：`plugins/social-group-participation/src/ailove_plugin_social_group_participation/plugin.py`。
- [ ] T095 [US5] 复读策略提供 AI 范围会话及固定模型预算。 路径：`plugins/social-group-repeat/src/ailove_plugin_social_group_repeat/plugin.py`。
- [ ] T096 [US5] QZone 策略提供人物关系依据与授权渠道动作。 路径：`plugins/social-qzone/src/ailove_plugin_social_qzone/plugin.py`。
- [ ] T097 [US5] Agent 装配使用稳定能力、独立实例与当前工具快照。 路径：`agent/ai_agent_service.py`、`agent/agent_supervisor.py`、`agent/extension_toolset_loader.py`。
- [ ] T098 [P] [US5] 导演插件提供确定场次及事件归属。 路径：`plugins/live-director-default/src/ailove_plugin_live_director_default/plugin.py`。
- [ ] T099 [P] [US5] Avatar 插件提供当前事件订阅与回调范围。 路径：`plugins/live-avatar-default/src/ailove_plugin_live_avatar_default/plugin.py`。
- [ ] T100 [P] [US5] Stream 插件提供当前事件订阅与回调范围。 路径：`plugins/live-stream-default/src/ailove_plugin_live_stream_default/plugin.py`。
- [ ] T101 [US5] 直播宿主以能力清单确定场次、设备和订阅结果。 路径：`live/director/director_service.py`、`live/edge_service.py`。
- [ ] T102 [US5] 人物与记忆视图采用公开查询及声明式贡献。 路径：`admin/console/backend/observability/people_memory.py`、`self_memory.py`、`personality.py`、`features/memory/people_page.tsx`、`self_page.tsx`、`features/personality/page.tsx`。
- [ ] T103 [US5] US5 具有各实际包公开入口与确定性业务对照证据。 路径：`output/plugin-architecture/us5.md`。
- [ ] T104 [US5] 完整目录与迁移资料定义配置、状态和旧包装器退出标准。 路径：`deployment/manifests/plugin-catalog.json`、`docs/plugin-migration.md`。
## Phase 8: 整体交付

- [ ] T105 31 包具有完整 wheel 资源、锁和产物索引。 路径：`scripts/plugins/build-artifacts.ps1`、`output/plugin-architecture/artifacts/index.json`。
- [ ] T106 部署清单分别表达核心、插件和 NapCat 的交付归属。 路径：`deploy/Dockerfile`、`deploy/docker-compose.yml`、`deploy/docker-compose.local.yml`、`deploy/docker-compose.cloud.yml`、`deploy/k8s/apps.yaml`、`deploy/nacos/service.gateway.yaml`、`service.ai-agent.yaml`、`service.extension-host.yaml`、`service.gptsovits.yaml`、`service.director.yaml`、`service.live-edge.yaml`。
- [ ] T107 最终代码依赖当前稳定契约，用户数据与迁移历史保留。 路径：`migration-adapters/`、`pyproject.toml`、`requirements.txt`、`shared/chat_model_strategy.py`。
- [ ] T108 架构证据覆盖直接/传递依赖、固定核心和空插件启动。 路径：`tests/plugin_architecture/test_boundaries.py`、`test_artifacts.py`。
- [ ] T109 联合恢复证据包含实际时间、来源水位和动作状态。 路径：`scripts/plugins/test-recovery.ps1`。
- [ ] T110 目标负载结果包含 P95、调用、token 与当前样本量。 路径：`scripts/plugins/test-load.ps1`。
- [ ] T111 31 包六项变更、100 次循环及 UI 验收具有对应证据。 路径：`deployment/manifests/plugin-catalog.json`、`admin/console/frontend/package.json`、`specs/002-plugin-architecture/acceptance.md`。
- [ ] T112 最终资料准确表达全部 FR、SC、入口与实际验收范围。 路径：`README.md`、`docs/plugin-authoring.md`、`docs/plugin-operations.md`、`specs/002-plugin-architecture/quickstart.md`、`output/plugin-architecture/final-report.md`。

## Dependencies

| 结果集合 | 前置结果 |
| --- | --- |
| T007～T020 | T001～T006 |
| US1 T021～T031 | 共同能力 |
| US2 T032～T040 | US1 及持久状态 |
| US3 T041～T051 | 生命周期及替换状态 |
| US4 T052～T063 | 资源、控制与实例边界 |
| US5 T064～T104 | 共同契约、管理、授权及隔离 |
| T105～T112 | 全部业务包与旧路径退出标准 |

## Result Prerequisites

| 结果任务 | 前置结果 |
| --- | --- |
| T008 | T007 |
| T009 | T008 |
| T011 | T010 |
| T012～T016 | 当前契约与持久控制结构 |
| T018 | T017 |
| T019 | T018 |
| T020 | T007～T019 |
| T023 | T021、T022 |
| T024、T025、T028 | T023 |
| T026、T027 | loader 与公开契约 |
| T029 | 正式安装及业务入口条件 |
| T031 | T029、T030 与 US1 其余结果 |
| T034、T035 | T032、T033 |
| T039、T040 | US2 候选、许可、账本及验收包 |
| T043、T044 | T041、T042 |
| T045、T046 | T043、T044 |
| T047～T049 | T045、T046 |
| T050、T051 | US3 控制与资源结果 |
| T054～T057 | T052、T053 |
| T059 | T058 |
| T060 | T059 |
| T061 | T060 |
| T062、T063 | US4 应用层结果 |
| T066 | T064、T065 |
| T074 | T067～T073 |
| T078、T079 | T075～T077 |
| T080 | T078、T079 |
| T088 | T081～T087 |
| T089 | T088 |
| T091 | T090 |
| T092 | T091 |
| T093～T096 | T092 |
| T097 | T093～T096 |
| T101 | T098～T100 |
| T103 | T102 与 US5 业务包 |
| T104 | T103 |
| T107 | T105、T106 与所有旧路径退出标准 |
| T108～T111 | T107 的最终产物 |
| T112 | 全部实际验收证据 |

## Requirement Coverage

| 需求 | 结果任务 | 验收范围 |
| --- | --- | --- |
| FR-001/002/003/023 | T002/004/019/021～031/105/107/108/111 | ACC-001～006/040 |
| FR-004/005/006/014 | T007～009/013/015/019/030/052/054/104/108 | ACC-007～012 |
| FR-007/008/009 | T010～012/023/034/039/041～051 | ACC-013～019 |
| FR-010/011/012/024 | T032～040/065/080/089～092/109 | ACC-020～026 |
| FR-013/015/016/017 | T014/015/018/052～057/062/063 | ACC-027～030/032 |
| FR-018/019 | T036/039/043～049/055/074/089/097/109/110 | ACC-017/022/023/031/032 |
| FR-020/025 | T021/024/025/028/058～063/102/111 | ACC-027/038 |
| FR-021/022 | T001/064～104/106/107/111/112 | ACC-033～040 |
