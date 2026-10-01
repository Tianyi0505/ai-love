# Tasks: 私聊交付结果清单

**状态**：38 项本地交付结果具有完成证据，发布数据见 [validation.md](validation.md)。
**标记**：勾选对应原有完成记录，任务编号、故事标签和独立范围保持原值。

## 基础资料

- [X] T001 基线资料具有实际分支、依赖、迁移 head、测试结果及普通文本调用量。 路径：`pyproject.toml`、`requirements.txt`、`alembic/versions/0005_lazy_lfu_state.py`、`specs/001-private-reply-rules/validation.md`。
- [X] T002 [P] 隔离夹具提供真实 PostgreSQL、受控时钟、平台事件与边界替身。 路径：`tests/conftest.py`、`tests/private_reply_fixtures.py`。
## 共同契约

- [X] T003 三张状态表具有接收序号、唯一键、扫描索引及 0..3 持久额度。 路径：`shared/database_models.py`、`alembic/versions/0006_private_reply_state.py`。
- [X] T004 [P] RPC 契约提供可信来源、固定 run_id、发送状态查询与结果码。 路径：`shared/contracts/rpc/social.py`、`shared/contracts/turn.py`、`shared/nats_bus.py`。
- [X] T005 [P] 恢复配置包含 5 秒扫描、100 批次、10 并发及处理/租约/心跳预算。 路径：`shared/service_settings.py`、`deploy/nacos/service.ai-agent.yaml`、`deploy/nacos/service.gateway.yaml`、`tests/test_agent_prompt_config.py`。
## User Story 1 — 全天私聊回应

- [X] T006 [P] [US1] 入口证据覆盖全天、各内容类型、关系状态、连续私信与澄清结果。 路径：`tests/test_private_reply_flow.py`。
- [X] T007 [P] [US1] 发送证据覆盖稳定键、请求摘要、有效来源及平台状态。 路径：`tests/test_social_delivery_recovery.py`。
- [X] T008 [US1] 入站事务提供唯一任务、首次归属、轮次重置及有序领取。 路径：`shared/private_interaction_repository.py`。
- [X] T009 [US1] 发送仓库提供固定摘要、原子资格、平台确认与查询结果。 路径：`shared/social_delivery_repository.py`。
- [X] T010 [US1] QQ 适配器提供准确平台状态和恢复资格。 路径：`gateway/qq_channel.py`。
- [X] T011 [US1] Gateway 入站提供有效私信持久快照、引用事实及 ready 唤醒。 路径：`gateway/gateway_message_handler.py`。
- [X] T012 [P] [US1] Gateway 发送提供原编号返回、历史凭证及最多两次安全恢复。 路径：`gateway/social_send_handler.py`、`shared/conversation_repository.py`。
- [X] T013 [US1] Gateway 提供 accepted 扫描、历史补记及状态查询生命周期。 路径：`gateway/gateway_service.py`。
- [X] T014 [US1] Agent 提供可感知回复、合法文字兜底及已生成文字保留。 路径：`agent/social/social_message_handler.py`、`agent/conversation/prompt_assembler.py`、`deploy/nacos/agent.default.yaml`。
- [X] T015 [US1] 私聊服务提供有效领取、45 秒预算、固定内容与核实状态。 路径：`agent/social/private_reply_service.py`。
- [X] T016 [US1] Agent 运行时提供统一领取、同会话顺序及独立资源生命周期。 路径：`agent/ai_agent_service.py`、`agent/ai_runtime.py`。
- [X] T017 [US1] US1 具有真实入口、恢复与已有行为的本地证据。 路径：`tests/test_private_reply_flow.py`、`tests/test_social_delivery_recovery.py`、`tests/test_gateway_message_handler.py`、`tests/test_agent_runtime.py`、`specs/001-private-reply-rules/validation.md`。
## User Story 2 — 主动联系额度

- [X] T018 [P] [US2] 主动状态证据覆盖额度、修订、并发、轮次及重启结果。 路径：`tests/test_private_contact_persistence.py`。
- [X] T019 [P] [US2] 调度证据覆盖作息、静默、冷却、话题和完整身份路由。 路径：`tests/test_proactive_private_service.py`。
- [X] T020 [US2] 联系仓库提供唯一预占、平台成功计数及 unknown 凭证。 路径：`shared/private_interaction_repository.py`。
- [X] T021 [P] [US2] 联系人候选采用同一 AI 绑定记录的 account/user/person。 路径：`shared/relationship_repository.py`、`shared/contracts/rpc/relationship.py`。
- [X] T022 [US2] 可信新联系人和历史联系人具有各自初始化依据。 路径：`shared/identity_repository.py`、`shared/private_interaction_repository.py`、`gateway/gateway_message_handler.py`。
- [X] T023 [US2] 主动策略提供最新轮次资格、固定来源与成功额度。 路径：`agent/social/proactive_private_service.py`。
- [X] T024 [US2] 主动对账提供 sent、failed、unknown 各自额度结果。 路径：`shared/social_delivery_repository.py`、`gateway/social_send_handler.py`、`agent/social/proactive_private_service.py`。
- [X] T025 [US2] 默认配置包含 1800 秒冷却与检查、21600 秒静默和固定 3 次额度。 路径：`agent/ai_runtime.py`、`deploy/nacos/agent.default.yaml`、`tests/test_agent_prompt_config.py`、`shared/contracts/agent.py`。
- [X] T026 [US2] US2 具有持久竞争、重启、清零与被动回应证据。 路径：`tests/test_private_contact_persistence.py`、`tests/test_proactive_private_service.py`、`tests/test_private_reply_flow.py`、`specs/001-private-reply-rules/validation.md`。
## User Story 3 — 当前引用目标

- [X] T027 [P] [US3] 引用证据覆盖当前 A、历史 B、多层引用及并发。 路径：`tests/test_social_quote_reply.py`。
- [X] T028 [US3] QQ 输入保留原始引用标记和历史归属。 路径：`gateway/qq_channel.py`、`gateway/content_type_resolver.py`。
- [X] T029 [US3] 执行上下文的带引用目标为当前 message_id。 路径：`shared/contracts/turn.py`、`agent/social/social_message_handler.py`。
- [X] T030 [US3] 引用降级具有确定平台依据、受控摘要修订和同一 run_id。 路径：`gateway/social_send_handler.py`、`shared/social_delivery_repository.py`。
- [X] T031 [US3] US3 具有出站引用与上下文正确性的回归证据。 路径：`tests/test_social_quote_reply.py`、`tests/test_group_message_json.py`、`tests/test_group_repeat.py`、`tests/test_qq_emoticons.py`、`specs/001-private-reply-rules/validation.md`。
## 交付证据

- [X] T032 180 天正文保留期具有最小去重凭证、额度与 unknown 资料。 路径：`shared/private_interaction_repository.py`、`shared/social_delivery_repository.py`、`gateway/gateway_service.py`、`tests/test_social_delivery_recovery.py`。
- [X] T033 观测结果包含 pending、回应覆盖、fallback、状态及模型调用量。 路径：`agent/social/private_reply_service.py`、`agent/social/proactive_private_service.py`、`gateway/social_send_handler.py`、`gateway/gateway_service.py`、`deploy/k8s/observability.yaml`、`tests/test_private_reply_observability.py`。
- [X] T034 [P] 迁移、重启、备份恢复与应用恢复保留持久状态。 路径：`tests/test_private_reply_migration.py`、`tests/test_private_contact_persistence.py`。
- [X] T035 [P] 10 会话 600 条负载具有完整归属、P95 与调用量证据。 路径：`tests/test_private_reply_load.py`。
- [X] T036 相关回归与静态检查具有有效结果。 路径：`specs/001-private-reply-rules/validation.md`。
- [X] T037 运行文档提供状态查询、核实依据、恢复标准及费用口径。 路径：`specs/001-private-reply-rules/quickstart.md`、`specs/001-private-reply-rules/operations.md`。
- [X] T038 FR、SC、架构与验收资料具有一致映射。 路径：`specs/001-private-reply-rules/validation.md`、`specs/001-private-reply-rules/plan.md`、`contracts/social-reply.md`。

## Dependencies

| 结果任务 | 前置结果 |
| --- | --- |
| T003～T005 | T001、T002 |
| T006、T007 | 共同契约与存储 |
| T008 | T003、T006 |
| T009 | T004、T007、T008 |
| T010 | T007、T009 |
| T011、T012 | T008～T010 |
| T013 | T005、T011、T012 |
| T014 | T006、T008、T012 |
| T015 | T005、T009、T014 |
| T016 | T013、T015 |
| T017 | T016 |
| T018、T019、T027 | T017 |
| T020、T021 | T018、T019 |
| T022 | T020、T021 |
| T023 | T022 |
| T024 | T023 |
| T025 | T024 |
| T026 | T025 |
| T028 | T027 |
| T029 | T028 |
| T030 | T029、T024 |
| T031 | T030 |
| T032 | 三个用户故事的交付结果 |
| T033～T035 | T032 |
| T036 | T033～T035 |
| T037 | T036 |
| T038 | T037 |

## Requirement Coverage

| 需求 | 结果任务 |
| --- | --- |
| FR-001～003 / SC-001 | T006～T017 |
| FR-004～009 / SC-002、SC-005 | T018～T026 |
| FR-010～011 / SC-003 | T027～T031 |
| FR-012～013 / SC-004、SC-006 | T032～T038 |
