# 研究记录

本记录基于本地真实调用链静态阅读，以及两个按 speckit-plan 要求并行执行的只读研究。没有运行线上复现、发送消息或修改业务代码。

## 1. 私信决策与异常路径

**Decision**: 保留私聊固定回复判断，补持久处理状态及无模型兜底。

**Rationale**: `agent/persona.py::should_respond_directly` 对 private 返回 True；`ai_runtime.py::handle_social` 已按会话锁调度后台任务。当前不能归因为“私聊概率不回复”或“忙碌直接丢弃”。`social_message_handler.py::_process` 在输入理解、上下文、生成、表情和 TTS 阶段可能异常；空 ResponsePlan 最终也可能无法发送。`gateway/qq_channel.py::_handle_message` 仅记录失败后跳过。这里确认的是静态可达异常路径，尚未运行故障复现。

**Alternatives considered**: 再添加一个是否回复判断无价值；把所有异常都重试整个轮次会重复工具动作；仅补 try/except 无法满足重投和恢复。

## 2. 可靠接收与去重

**Decision**: 私信任务保存在现有 PostgreSQL，NATS 仅快速唤醒，定时扫描恢复。

**Rationale**: `gateway_message_handler.py::handle` 在补全之后才记入站并 publish；`conversation_repository.py::record_inbound` 唯一键只防重复历史写入，不阻止继续 publish。`ai_agent_service.py` 使用普通 subscribe_model，AIRuntime spawn 不代表处理完成。仓库虽有 durable 方法，本特性不必同时维护数据库任务与新增 JetStream 消费语义。

**Alternatives considered**: 内存集合无法跨重启；单靠 Message 行无法恢复完整引用内容和执行阶段；JetStream 仍需处理去重/发送记录，增加一套恢复机制，未选。

## 3. 主动限额与身份

**Decision**: 专用 PostgreSQL 状态以 (ai_id, person_id) 唯一，固定最多 3 次，默认冷却 1800 秒。

**Rationale**: `proactive_private_service.py::run_once` → `SessionManager.can_initiate`：replied=false 即停止，且 hash 有 TTL；默认检查 1800、安静期 21600、冷却 43200 秒，`ailove.config.yaml` 中 session TTL 为 2592000 秒。未发现自然日锁。群聊也调用 SessionManager，不能把其语义统一改为 3 次。

`relationship_repository.py::list_people` 用独立子查询取 user/account；主动场景硬编码 QQ。设计改为从一条完整且属于当前 AI 绑定账号的可信 QQ 身份选择路由，复用 PlatformIdentity/Person，不进行新身份合并。Agent 服务已持有 Database，可注入专用 shared 仓库，无需让 Memory 持有社交额度，也无需额外远程状态服务。

**Alternatives considered**: Redis 加 counter 仍有过期/恢复与身份键问题；按 user_id 或昵称会混淆账号或人物；修改关系分数模型超出需求。

## 4. 发送结果未知

**Decision**: Gateway 按稳定 run_id 保存发送阶段，重复请求查已有结果；unknown 不自动重发。

**Rationale**: `social_send_handler.py::send` 先 channel.send 再 record_outbound；后者失败会掩盖已经发送。`SocialSendResponse` 仅 message_id，历史无 run_id。QQ 返回 HTTP 成功和平台 message_id 才确认，不能依据 RPC 超时认定未发。QQ 声明不支持历史能力，已有 get_msg 需要已知 message_id，不能凭客户端操作号自动找回丢失结果。

**Alternatives considered**: 所有超时直接重发会重复；先加次数永久不回退会把未发送计为成功；跨数据库和 QQ 的原子事务不可用。采用短事务预占、明确确认、未知暂停。

## 5. 引用链

**Decision**: 出站目标引用当前 A；历史 B 保留在 quote_ref。保留入站引用标记，补全失败仍能识别 A 带引用。

**Rationale**: `QuoteStrategy.apply` 写 reply_message_id；`QQChannel._hydrate_quote` pop 并加载 B；`AgentExecutionContext.from_social_message` 使用 quote_ref.message_id；`social_message_handler` 原样传递到 `ResponseCommand`；`QQChannel.send` 转为平台 reply 段。这是 A 引用 B 时当前链路静态可达的错误目标来源。

**Alternatives considered**: 将 B 替换成 A 的内容会破坏理解上下文；所有消息统一加引用会改变无引用消息展示，不选。

## 6. 准入与迁移

**Decision**: 实施规格中有效私信范围的最小准入；历史主动状态保守迁移。

**Rationale**: 当前 whitelist 在 Gateway 中只是 priority_contact，未核实到私信拒绝执行点；自身消息也需明确排除。不得宣称防护已存在。迁移前暂停主动，为旧联系人建立 suspended；新私信初始化 0。旧历史不能区分主动/被动，因此不凭它推断历史次数。普通缺行不是新联系人，禁止自动释放额度。

**Alternatives considered**: 全体初始化 0 可能立刻继续打扰已未回复用户；从总 AI 消息数推断主动次数没有证据。

## 7. 界限与已解决事项

全部设计未知已通过代码核查或明确默认值解决，无待澄清项。真实线上故障发生率、实际模型计价与目标部署资源属于后续上线测量，不能在设计阶段声称已验证。保持现有依赖版本，不涉及技术升级或新服务选型，无需互联网资料替代仓库事实。
