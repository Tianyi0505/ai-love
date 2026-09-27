# Tasks: 私聊必回复、主动联系限额与引用目标修正

**Input**: `specs/001-private-reply-rules/` 中的 [spec.md](spec.md)、[plan.md](plan.md)、[research.md](research.md)、[data-model.md](data-model.md)、[接口契约](contracts/social-reply.md)、[quickstart.md](quickstart.md)。

**Prerequisites**: 上述设计已完成；当前实际分支为 `main`。本清单按当前宪章 1.3.0 核对，复用现有适配器和服务组合，状态转换集中到专用仓库，不引入空接口或通用工作流框架。

**Tests**: 规格明确要求真实入口、并发、重启、故障和量化负载验收，因此包含对应测试任务；先写场景并确认失败来自目标行为，再实现。平台与模型使用本地替身，持久化竞争使用真实隔离 PostgreSQL；不能把内部方法测试当作生产复现。

**Organization**: 共 38 项，按基础工作、US1、US2、US3、交叉验证分组。实施结果与证据记录在 `validation.md`。

## Format: `[ID] [P?] [Story] Description`

- `[P]` 表示在列出的前置任务完成后，可与同批不同文件任务并行，不表示可跳过依赖。
- `[US1]`：私聊必回复（P1）；`[US2]`：主动联系最多连续 3 次（P2）；`[US3]`：回复引用当前消息（P2）。
- 下列文件路径相对仓库根目录 `D:\ai-love`；标记“新增”的文件由相应任务创建。
- 执行范围是本地实现和验证；不推送、不创建远程 Issue/PR、不部署、不实际发信。不自动提交；若另有提交要求，遵循约定式提交。

## Phase 1: Setup（准备与基线）

**Purpose**: 复用现有 Python、数据库和测试体系，准备可对比的证据，不重新初始化项目。

- [X] T001 核对 `pyproject.toml`、`requirements.txt`、`alembic/versions/0005_lazy_lfu_state.py` 和现有测试，运行 quickstart 中的既有本地回归；在新增 `specs/001-private-reply-rules/validation.md` 记录实际分支、迁移 head、测试基线、正常文本模型调用基线与环境缺项，避免把既有失败归于本特性。
- [X] T002 [P] 在 `tests/conftest.py` 与新增 `tests/private_reply_fixtures.py` 建立隔离 PostgreSQL schema、受控时钟、平台格式事件、模型/HTTP/NATS 替身及服务装配夹具；仅从 `AILOVE_TEST_DATABASE_URL` 获取测试库，拒绝生产目标，禁止真实网络发信，不 mock 掉待验证的事务与入口逻辑。

## Phase 2: Foundational（共同契约与存储）

**Purpose**: 固定共享模型和接口，让后续实现围绕明确边界展开。

依赖 T001、T002；T003、T004、T005 文件不重叠，可并行。完成后才进入用户故事实现。

- [X] T003 在 `shared/database_models.py` 与新增 `alembic/versions/0006_private_reply_state.py` 按 data-model 定义 PrivateReplyJob、PrivateContactState、SocialDelivery、接收序号、唯一键和扫描索引；入站唯一键不含 ai_id，主动计数限定 0..3 且无 TTL，引用降级保留修订标记；旧联系人初始化 suspended、不重建历史次数、不删旧 Redis。若迁移 head 已变化，选下一个可用 revision 并更新文档引用，不覆盖他人迁移。
- [X] T004 [P] 在 `shared/contracts/rpc/social.py`、`shared/contracts/turn.py` 定义可靠私聊来源字段、发送状态查询请求/响应和明确错误类型；保持成功响应 message_id，默认字段不改变非私聊语义，运行时传递固定 run_id/job/claim/person。沿用 `shared/nats_bus.py` 的错误 envelope；仅在现有编码不足以保留错误类型时最小修改，禁止将超时归为已知未发送。
- [X] T005 [P] 在 `shared/service_settings.py`、`deploy/nacos/service.ai-agent.yaml`、`deploy/nacos/service.gateway.yaml` 加入恢复扫描 5 秒、批次 100、并发 10、处理预算 45 秒、租约 120 秒、心跳 15 秒和最多 2 次明确未发恢复配置；只做必要正值/时间关系校验，在 `tests/test_agent_prompt_config.py` 验证配置装配，不修改远程 Nacos。

**Checkpoint**: 模型可迁移、接口可装配、配置可加载；新增契约要求 Gateway/Agent 同版本，不以 extra=forbid 下的默认值声称旧服务能接受新字段。

## Phase 3: User Story 1 — 每条有效私信都有回应（P1，MVP）

**Goal**: 持久接收、去重、有序处理、非空回应和安全恢复；即使主动额度满也能回应。

**Independent Test**: 使用真实入口装配和本地替身，覆盖工作内外、当前支持的非文本输入、空生成/模型/TTS失败、连续私信、重投、丢唤醒、发送确认丢失和重启；每个独立有效私信有唯一回应归属，未知送达不自动重发。

### Tests for User Story 1

- [X] T006 [P] [US1] 在新增 `tests/test_private_reply_flow.py` 编写入口集成测试：白名单与自身回流边界、所有支持输入类型、工作内外、低关系、额度满、连续消息、账号换绑后的重投、增强失败、空生成、模型失败、附属写入失败；断言非空回应、一次清零、无重复关系/记忆副作用和既有群聊行为保留，先记录目标行为失败。
- [X] T007 [P] [US1] 在新增 `tests/test_social_delivery_recovery.py` 编写发送/查询契约及数据库恢复测试：固定键重入、同键异内容冲突、越权查询、旧 claim、历史写入失败、RPC 丢响应、未知网络结果和有限安全重试；验证 sending 切换时原子校验来源，查询本身不发送。

### Implementation for User Story 1

- [X] T008 [US1] 在新增 `shared/private_interaction_repository.py` 实现首次接收与主动清零的单事务、固定 AI/run_id、重复输入返回原任务、同会话最早接收序领取、版本化租约/心跳和状态转换；新私信保留冷却时间，取消尚未外发预占但不释放 sending/unknown；旧 AI 不可处理时明确暂停并可定位。依赖 T003、T006。
- [X] T009 [US1] 在新增 `shared/social_delivery_repository.py` 实现固定发送键、不可变快照/摘要、原子 prepared→sending、确认持久化、状态查询及失败分类；同一事务锁定来源 Job/ContactState 并复核 claim/pending，制定统一锁顺序避免与入站清零死锁，所有外部调用均在事务外。依赖 T004、T007、T008。
- [X] T010 [US1] 在 `gateway/qq_channel.py` 将发送前拒绝、确定未发送的暂时失败、平台确认与无确认网络失败分类，结果未知不自动重试；保留 QQ 协议适配职责与非私聊行为，错误类型通过 T004 契约传递。依赖 T007、T009。
- [X] T011 [US1] 在 `gateway/gateway_message_handler.py` 接入有效私信准入和先保存后增强：仅排除自身回流与无编号事件，关系白名单不拦截私信；固定首次 AI 归属、生成完整入站快照、首次事务清零、重复事件不重新发布/更新关系；hydrate/grounding 失败保留当前消息并只允许安全澄清，ready 后用原 NATS 主题唤醒。保持名单内容、群聊和直播路由不变。依赖 T008、T010。
- [X] T012 [P] [US1] 在 `gateway/social_send_handler.py`、`shared/conversation_repository.py` 接入持久发送与只读查询：sent 直接返回原编号，先保存确认再可补偿记历史，只有确定未发的暂时失败按 5/15 秒最多重试 2 次；sending/unknown 不外发，异内容与失效来源拒绝。非私聊保留原路径。依赖 T009、T010。
- [X] T013 [US1] 在 `gateway/gateway_service.py` 注入仓库、注册 `social.send.status.request`、启动 accepted 与历史补记恢复扫描；丢失唤醒可重建，超时 sending 标记 unknown，扫描异常不中止后续扫描，数据库不可用停止成功接收声明；扫描生命周期随服务退出收拢。依赖 T005、T011、T012。
- [X] T014 [US1] 在 `agent/social/social_message_handler.py`、`agent/conversation/prompt_assembler.py` 与 `deploy/nacos/agent.default.yaml` 实现非空回复与配置化文字兜底；将可恢复的生成/理解/表情/语音失败与发送阶段区分，优先保留已生成文字，禁止兜底再调用模型；关系/记忆附属失败不把 sent 改为未发，首次任务控制副作用，不修改群聊参与规则。依赖 T006、T008、T012。
- [X] T015 [US1] 在新增 `agent/social/private_reply_service.py` 实现私信任务领取、45 秒处理预算、心跳、最终内容保存、查询后恢复及安全终态；中断生成不重放工具，prepared 重用固定内容/run_id，语音降级只允许发送记录创建前原子改为文字；旧 worker 失去 claim 后不能提交，unknown 告警且不挡住后续私信。依赖 T005、T009、T014。
- [X] T016 [US1] 在 `agent/ai_agent_service.py`、`agent/ai_runtime.py` 装配私信服务与仓库，NATS 唤醒和扫描统一进入领取路径，保留会话锁、每批100/并发10及积压顺序；热加载/停机取消并收拢任务，重启扫描安全状态而不重置额度，移除私聊重复 Redis mark_replied，保留群聊 SessionManager。依赖 T013、T015。
- [X] T017 [US1] 执行 `tests/test_private_reply_flow.py`、`tests/test_social_delivery_recovery.py`、`tests/test_gateway_message_handler.py`、`tests/test_agent_runtime.py` 的入口与重启场景，补充丢唤醒、过期 worker、迟到生成和处理中工具中断覆盖；在 `specs/001-private-reply-rules/validation.md` 记录命令、结果和模拟边界，缺少真实数据库时不得标记完成。依赖 T016。

**Checkpoint**: US1 单独可验证；主动发送尚沿用旧策略或关闭，但有效私信不依赖 US2 完成。先完成此 MVP 的功能验证，完整发布仍需最终阶段相关保障。

## Phase 4: User Story 2 — 一天多次主动联系、连续未获回复最多3次（P2）

**Goal**: 按 AI 与联系人持久限额，保留作息、安静期和合理冷却，避免跨日/重启/并发突破上限。

**Independent Test**: run_once→真实持久层→Gateway→平台替身，在同日允许第2/3次、阻止第4次；新有效私信清零、旧事件/他人/群消息不清零；跨日重启不丢计数，未知发送冻结主动但不阻断被动。

### Tests for User Story 2

- [X] T018 [P] [US2] 在新增 `tests/test_private_contact_persistence.py` 编写真实数据库场景：计数0..3、不同AI/联系人隔离、两连接争抢最后额度、入站与预占/sending交错、跨日/重启/TTL、旧联系人迁移、普通缺行、新身份创建、已sent未提交计数恢复；先记录目标行为失败。依赖 T017。
- [X] T019 [P] [US2] 在 `tests/test_proactive_private_service.py` 补调度与可信路由测试，保留关系/话题判断的原覆盖，增加6小时安静期、30分钟冷却、作息、未绑定账号、完整身份选择、无话题/空生成/明确失败不计数和组合输出只计一次；关系白名单仅保留既有优先级语义。依赖 T017。

### Implementation for User Story 2

- [X] T020 [US2] 在 `shared/private_interaction_repository.py` 增加资格快照、版本复核、唯一预占、成功计数与安全释放；相同run_id确认只能提交一次，count=3拒绝第4次，无TTL，未知保留pending；对发送与用户回复顺序无法证明的情况保存unknown，不按ACK时间猜测。依赖 T018、T019。
- [X] T021 [P] [US2] 在 `shared/relationship_repository.py` 一次选择属于当前AI绑定账号的完整可信QQ身份 account/user/person，禁止独立子查询拼错路由；如需传递平台字段同步 `shared/contracts/rpc/relationship.py`，不更改关系分数算法或人物身份合并。依赖 T018、T019，可与 T020 并行。
- [X] T022 [US2] 在 `shared/identity_repository.py`、`shared/private_interaction_repository.py` 和 `gateway/gateway_message_handler.py` 接通可信新联系人初始化来源：真正新建可为active/0，历史联系人无状态为suspended，首次有效私信仅解除迁移暂停而不释放未知发送；复用T003迁移，重复初始化不重置次数。依赖 T020、T021。
- [X] T023 [US2] 在 `agent/social/proactive_private_service.py` 接入持久资格与预占，生成后发送前重新检查作息/安静期/冷却/回复版本，有新私信则取消旧话题；固定最多3次，发送携带可信来源和稳定run_id，空生成不占额，不再调用主动Redis门闩。依赖 T022。
- [X] T024 [US2] 在 `shared/social_delivery_repository.py`、`gateway/social_send_handler.py` 和 `agent/social/proactive_private_service.py` 完成主动发送结果对账：sent确认幂等计数、明确未发释放、unknown冻结，预占与发送切换共享事务校验；恢复时查询已有run_id而非换号重发，发送前失效预占拒绝。依赖 T023。
- [X] T025 [US2] 在 `agent/ai_runtime.py` 注入主动状态依赖，在 `deploy/nacos/agent.default.yaml` 将 private_cooldown_sec 从43200改1800，保持interval=1800/quiet=21600/work_hours；更新 `tests/test_agent_prompt_config.py` 的默认值契约，复核 `shared/contracts/agent.py` 不引入可放宽3次上限的配置。依赖 T024。
- [X] T026 [US2] 执行 `tests/test_private_contact_persistence.py`、`tests/test_proactive_private_service.py` 并回归 `tests/test_private_reply_flow.py`，验证真实入口清零、并发/重启、未知发送与新私信共存；在 `specs/001-private-reply-rules/validation.md` 记录证据，不能仅用mock sessions证明限额可靠。依赖 T025。

**Checkpoint**: US2 完成且 US1 回归通过；不以跨日或状态清理释放主动额度。

## Phase 5: User Story 3 — 回复引用当前消息（P2）

**Goal**: A引用B时，AI正常回复引用A，同时保留B的上下文。

**Independent Test**: 平台格式引用输入→hydrate→Agent→最终QQ发送段，覆盖私聊/群聊、多层引用、历史缺失与并发会话；无引用、主动消息、群复读维持原展示。

### Tests for User Story 3

- [X] T027 [P] [US3] 在新增 `tests/test_social_quote_reply.py` 写入口链路测试：A引用B、B引用C、不同发送者、B不存在/补全超时、当前A不可引用、并发会话、普通无引用/主动/群复读；断言最终reply编号为A且历史上下文仍为B，先记录错误目标失败。依赖 T017；可与 T018、T019 并行。

### Implementation for User Story 3

- [X] T028 [US3] 在 `gateway/qq_channel.py` 保留原始 `meta.reply_message_id`，hydrate不再pop丢失引用存在标记；历史补全失败保留A和必要错误状态，复用已有循环防护；结合 `gateway/content_type_resolver.py` 的既有QuoteStrategy保证标记来源是平台输入。依赖 T027。
- [X] T029 [US3] 在 `shared/contracts/turn.py` 将带引用消息的 reply_to_message_id 设为当前message_id，兼容原始标记存在但quote_ref缺失的输入；在 `agent/social/social_message_handler.py` 透传执行上下文，不改quote_ref内容或其他发送者归属，不给普通无引用消息额外加引用。依赖 T028。
- [X] T030 [US3] 在 `gateway/social_send_handler.py`、`shared/social_delivery_repository.py` 实现仅“明确引用不可用且已证明未发送”时一次移除引用的受控修订；同一run_id记录修订前后摘要，重复调用可识别该修订，未知结果/普通内容变更不重发，当前编号协议无效时普通回应。依赖 T029、T024。
- [X] T031 [US3] 执行 `tests/test_social_quote_reply.py`、`tests/test_group_message_json.py`、`tests/test_group_repeat.py`、`tests/test_qq_emoticons.py` 及私信回归，核验最终平台请求和上下文同时正确；在 `specs/001-private-reply-rules/validation.md` 记录每类引用场景结果。依赖 T030。

**Checkpoint**: 三个故事的独立场景均有真实入口证据，群聊参与/复读未被主动私聊状态影响。

## Phase 6: Polish & Cross-Cutting Concerns（恢复、运维与验收）

**Purpose**: 完成本次功能所需的生产保障，不扩展到无关服务重构。依赖三个故事功能完成。

- [X] T032 在 `shared/private_interaction_repository.py`、`shared/social_delivery_repository.py` 与 `gateway/gateway_service.py` 实现按既有180天保留期清理正文快照，保留最小去重凭据、终态与主动计数，未解决unknown保留必要定位；在 `tests/test_social_delivery_recovery.py` 增加清理后重投不再回复、不过期释放额度的验证。
- [X] T033 在 `agent/social/private_reply_service.py`、`agent/social/proactive_private_service.py`、`gateway/social_send_handler.py`、`gateway/gateway_service.py` 接入现有可观测设施，提供pending年龄/数量、回应覆盖、fallback、unknown、失败和模型调用指标及原因日志；在 `deploy/k8s/observability.yaml` 配置或接入pending>60秒/任意unknown/连续3次失败/扫描失败告警，并在新增 `tests/test_private_reply_observability.py` 验证无敏感正文与凭据泄露。依赖 T032。
- [X] T034 [P] 在新增 `tests/test_private_reply_migration.py` 与 `tests/test_private_contact_persistence.py` 演练旧数据增量迁移、各持久阶段停机重启、备份恢复到隔离schema和应用回滚保留新表；要求普通重启已确认状态RPO=0、恢复后60秒内处理安全任务或显示待核实，旧数据/关系/记忆不变。依赖 T032，可与 T033 并行。
- [X] T035 [P] 在新增 `tests/test_private_reply_load.py` 编写并执行10会话均匀轮转、1条/秒持续600秒的入口负载场景，模型<=2秒、发送<=1秒；输出本地负载汇总，要求600条归属完整、P95<=10秒、错误/重复/超发为0、普通文本模型调用比值<=1，故障样本分开统计。依赖 T032，可与T033/T034开发并行；实际负载运行须避开其他共享数据库性能测试。
- [X] T036 完成相关回归与代码检查，在 `specs/001-private-reply-rules/validation.md` 记录quickstart所列测试、新增迁移/告警测试及对变更Python文件的ruff结果；验证Group SessionManager、平台路由、权限、固定run_id、数据生命周期和新旧RPC不混跑，失败修复后仅重跑受影响范围。依赖 T033、T034、T035。
- [X] T037 在 `specs/001-private-reply-rules/quickstart.md` 与新增 `specs/001-private-reply-rules/operations.md` 固化可执行的本地验证、状态只读查询、unknown凭证核查、备份恢复、旧联系人暂停、Gateway/Agent协同升级和保留新表的回滚流程；说明无权威凭证不能解除未知状态或重发，记录真实模型单价/费用的上线验收表，缺少单价明确未验收，不编造、不执行真实发布。依赖 T036。
- [X] T038 在 `specs/001-private-reply-rules/validation.md` 完成FR-001～013、SC-001～006与实际测试证据的对照和宪章1.3.0架构复核：协议适配留在Channel、决策留在Agent、状态集中仓库，说明接口破坏范围及调用方同步；更新必要的 `specs/001-private-reply-rules/plan.md` / `contracts/social-reply.md` 与实际实现一致，明确未执行的线上验收和发布阻断项。依赖 T037。

## Dependencies & Execution Order

### Phase Dependencies

```text
准备 T001/T002
      ↓
基础 T003/T004/T005
      ↓
US1 T006–T017（MVP）
      ├───────────────┐
      ↓               ↓
US2 T018–T026     US3 T027–T029
      │               │
      └─ T024 ───────→T030→T031
              ↓
收尾 T032→(T033 / T034 / T035)→T036→T037→T038
```

### User Story Dependencies

- US1 不依赖 US2 的主动调度或 US3 的引用目标修正，可独立实现非空回应。其入站清零支持迁移和额度满场景，属于共用状态的一部分。
- US2 复用 US1 的可靠入站、发送状态和查询；必须在 T017 后实施，不能声称完全无依赖。
- US3 的引用测试及标记/目标修正可在 T017 后与 US2 非冲突任务推进；T030 修改共享发送模块，等待 T024 后进行，避免并行写同一文件。
- 收尾不是可选装饰：相关恢复、负载、监测未通过前不得宣称生产验收完成。

### Within Each User Story

- 场景测试先形成可运行失败证据，再实现；导入失败或测试夹具损坏不能冒充业务失败。
- US1 顺序为 T006/T007 → T008 → T009 → T010 → T011/T012 → T013 → T014 → T015 → T016 → T017；T011/T012不同文件，可在T010后并行，但T013等二者完成。T006/T007属于US1测试任务。
- US2 顺序为 T018/T019 → T020/T021 → T022 → T023 → T024 → T025 → T026。
- US3 顺序为 T027 → T028 → T029 → T030 → T031，T030另依赖T024。
- 新增迁移、错误类型和配置先于调用方接入；真实外部写入不在任何任务的隐含授权范围内。

### Parallel Opportunities

所有并行例子只描述后续执行机会，不要求本次创建代理。只有前置条件完成且文件不重叠才适用；共享数据库的负载与恢复演练需使用不同实例或串行执行。

## Parallel Example: User Story 1

在基础阶段完成后，T006编写 `tests/test_private_reply_flow.py` 与T007编写 `tests/test_social_delivery_recovery.py` 可并行；夹具修改先统一合入T002，避免两者同时改conftest。T010完成后T011接收逻辑与T012发送处理也可并行。

## Parallel Example: User Story 2

T017后T018持久状态测试与T019调度测试可并行；两者完成后T020实现状态仓库与T021实现完整身份查询可并行，T022等待二者完成。

## Parallel Example: User Story 3

T017后T027引用入口测试可与T018/T019并行。T028修改QQ引用补全时可与T020/T021并行；T029涉及公共执行上下文及handler，与其他修改这些文件的任务串行。T030必须等待T024，不将共享发送修改误标为可并行。

## Implementation Strategy

### MVP First（US1）

先执行T001～T017，得到可靠非空私聊回应的独立验证结果。此检查点是最小功能增量，不代表原始三个需求全部完成，也不授权部署。

### Incremental Delivery

完成US1后接US2，再整合US3；按依赖允许测试和不冲突代码并行。三个故事通过后完成T032～T038，分别报告本地实现、受控端到端证据、真实数据库验证与尚未执行的线上验收。

### Requirement Coverage

| 需求/标准 | 主要任务 | 验收任务 |
| --- | --- | --- |
| FR-001～002 / SC-001 | T011、T014～T016 | T006、T017 |
| FR-003 / SC-005去重顺序 | T003、T008～T013、T015～T016 | T006～T007、T017、T034 |
| FR-004～005 / SC-002 | T008、T020、T023～T025 | T018～T019、T026 |
| FR-006身份归属 | T008、T021～T022 | T006、T018～T019、T026 |
| FR-007～009 / SC-005限额恢复 | T009、T012、T020、T022～T025 | T007、T018、T026、T034 |
| FR-010～011 / SC-003 | T028～T030 | T027、T031 |
| FR-012追踪与有限恢复 | T009～T016、T024、T033 | T007、T017、T033～T034 |
| FR-013范围与长期状态边界 | T003、T016、T021、T028～T033 | T026、T031、T034、T036、T038 |
| SC-004负载 | T015～T016 | T035～T036 |
| SC-006调用与成本 | T001、T014、T023 | T035～T038；实际单价缺失单列上线阻断 |

## Notes

- 38 项本地实施任务已完成；真实部署、真实 QQ 发信和缺少单价的货币成本验收仍按 `validation.md` 标记为未执行或阻断。
- 不将宪章更新扩展成无关重构；已有Channel适配器和服务组合足够，状态转换用明确仓库方法表达，不为每个状态创建空类。
- 当前未配置 `.specify/extensions.yml`，before_tasks与after_tasks钩子均跳过。



