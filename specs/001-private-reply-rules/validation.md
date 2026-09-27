# 实施验证记录

## 基线与环境

- 实际分支：`main`。开始时业务代码无未提交修改；`.agents/`、`.specify/`、`specs/` 是已有未跟踪目录。
- Python 3.11.9；实施前迁移 head 为 `0005_lazy_lfu_state`。
- 基线命令：`.venv/Scripts/python.exe -m pytest tests/test_agent_runtime.py tests/test_gateway_message_handler.py tests/test_proactive_private_service.py tests/test_model_failover.py tests/test_group_repeat.py tests/test_group_message_json.py tests/test_qq_emoticons.py -q`。
- 基线结果：37 passed in 17.50s。普通文本路径每条调用一次 `generate_plan`，没有调用真实模型。
- requirements checklist 为 16/16；没有 `.specify/extensions.yml`，实施前后均无扩展钩子。
- 持久层测试使用本机 `private_reply_test` 数据库的逐测试隔离 schema。夹具拒绝非 localhost 或名称不以 `_test` 结尾的数据库。

## 已验证行为

| 范围 | 证据 |
| --- | --- |
| 私信必回复 | QQ 平台格式事件经过 Channel→Gateway→持久任务→Agent→Gateway→HTTP 替身。正常、空生成、模型失败、输入失败、图片、语音、文件、引用、转发均产生非空回应；非关系白名单用户同样回复，自身回流被排除。 |
| 去重与顺序 | 相同入站事件只建立一个任务并只发送一次；3 条同会话消息按 `received_seq` 领取；丢失 NATS 唤醒后扫描可恢复。 |
| 发送恢复 | 固定 `(ai_id, account_id, run_id)` 重入返回原平台编号；异内容冲突；历史补写失败不重发；读超时标记 unknown 且不自动重试；只有明确未发失败使用有限重试。 |
| 主动私聊 | 持久计数允许未回复时第 1、2、3 次，阻止第 4 次；跨日和仓库重建不清零；新有效私信清零；重复私信、其他联系人及群消息不清零。并发调度只取得最后一个额度。 |
| 主动对账 | 生成期间收到新私信会使旧预占失效；发送结果未知或 RPC 未到 Gateway 时冻结对应联系人，但后续被动私信仍可回复；可信路由的 account/user/person 来自同一条当前 AI 绑定身份。 |
| 引用 | A 引用 B 时保留 `meta.reply_message_id=B` 与 `quote_ref=B` 供上下文使用，最终 QQ reply 段为 A；B 缺失仍回复 A；多层引用不沿链回退。平台明确拒绝 A 的引用且确认未发送时只移除引用一次。 |
| 保留期 | 180 天后只清理已终结任务及已补写历史发送的正文快照；去重键、终态、平台编号和主动计数保留，清理后重投不会再次回复。unknown 快照保留。 |
| 观测 | 指标覆盖接收、结果、fallback、模型调用、pending 数量/年龄、扫描失败、发送和主动结果。pending 超过 60 秒、任意 unknown、连续 3 次失败和扫描失败产生日志告警；测试确认异常正文、消息正文和凭据不进入标签或告警日志。 |

## 数据库迁移演练

使用仓库 `deploy/docker-compose.yml` 锁定的 `pgvector/PostgreSQL 16.15` 镜像和独立的 `private_reply_migration_test` 数据库：

1. 从空库执行 `python -m alembic upgrade head`，结果为 `0006_private_reply_state`；三张新表均存在。
2. 从 `0005_lazy_lfu_state` 状态模拟真实旧库，保留一条旧 `person_relationships` 后执行 `upgrade head`。原关系行仍为 1 条；新状态为 `ai-old|42|suspended|0|migration`。
3. 首次空库演练发现仓库 `0001` 会读取当前 ORM 元数据，导致 `0006` 重复建表；`0006` 改用 `IF NOT EXISTS` 后从空库和旧 head 两条路径均通过。
4. 使用 `pg_dump -Fc` 备份升级库并恢复到独立 `private_reply_restore_test`：head、旧联系人状态和关系行数完全一致。
5. `downgrade()` 明确拒绝删除可靠状态；应用回滚保留三张表。

## 验证命令与结果

- 首轮 US1 入口/恢复及既有 Gateway/Agent 回归：24 passed in 21.88s。
- 主动状态与调度：7 passed in 14.19s；补充可信路由后 7 passed in 15.19s。
- 引用入口与既有补全：12 passed in 10.59s。
- 观测、发送清理与主动状态组合：14 passed in 21.79s。
- 配置契约：8 passed in 5.32s。
- 最终全量回归：161 passed, 1 skipped in 72.49s；跳过项是默认关闭、且已单独通过的十分钟负载测试。
- `ruff check` 覆盖所有变更 Python 文件，通过。
- `python -m compileall -q agent gateway shared alembic tests`，通过。
- `kubectl kustomize deploy/k8s`，通过；`observability.yaml` 已纳入 kustomization，并开放 Jaeger 8888 监测端口。
- 10 分钟持续负载：1 passed in 606.29s。持续 600.026 秒处理 600 条，全部 sent，平台请求 600、唯一 run_id 600、P95 0.098 秒、模型调用 600、每条调用比值 1.0。

## 需求与成功标准对照

| 条目 | 本地证据 | 状态 |
| --- | --- | --- |
| FR-001～003 / SC-001 | 必回复、非空兜底、支持输入、连续消息、非优先用户、去重与有序入口测试 | 通过 |
| FR-004～009 / SC-002、SC-005 | 持久额度、冷却/安静期/作息、可信路由、并发预占、重启/跨日、回复清零、unknown 冻结 | 通过 |
| FR-010～011 / SC-003 | 私聊入口、缺失历史、多层引用、一次安全降级及群聊引用回归 | 通过 |
| FR-012～013 | 状态查询、有限重试、保留期、低敏观测、Group SessionManager 与复读回归 | 通过 |
| SC-004 | 10 会话、1 条/秒、600 秒负载；600/600 有回应，P95 0.098 秒，错误/重复/超发为 0 | 通过 |
| SC-006 模型调用 | 普通样本每条最多一次模型计划调用；故障兜底零额外模型调用 | 通过 |
| SC-006 货币成本 | 官方 tokenizer 复核真实卡住文档：结构化完整输出至少 4341 token，大于原 4096 上限 | 根因已修复并上线；精确历史 token 台账仍缺失 |

## 架构与边界

- QQ 协议解析、引用段和平台错误分类保留在 Channel；必回复、fallback 和主动联系决策在 Agent；跨进程状态集中在两个专用仓库。
- 群聊继续使用 Redis `SessionManager`，私聊额度不使用 TTL；没有引入新服务、通用工作流或新的身份合并逻辑。
- 新 RPC 字段在 `extra=forbid` 下要求 Gateway 与 Agent 同版本升级；不能新旧混跑。
- 自动测试没有连接真实 Nacos、NATS、模型或 QQ 账号，没有执行真实发信、部署或任何外部写入。平台永久不可用时只能保证任务可定位，不能承诺送达。

## 2026-09-11 生产发布与费用修复

- 发布前数据库备份：`/opt/ailove/backups/pre-private-reply-20260911-1232.dump`，已验证 SHA-256，并由 `pg_restore --list` 读取 158 项。
- 数据库迁移已执行到 `0006_private_reply_state (head)`；Gateway 为 `ailove/gateway:private-reply-20260911-1232`，AI Agent 最终为 `ailove/ai-agent:private-reply-20260911-1232-r3`，均 Ready 且无重启。
- Nacos 仅更新私聊恢复配置、主动冷却、文字兜底、记忆失败退避，以及记忆专用 16384 token/240 秒预算；每次发布均保存前后配置并回读一致。NapCat 未重启，持续运行三周。
- Edge 节点仍为 NotReady，`extension-host` 无 responder；AI Agent 对该已知依赖缺失使用空扩展集启动，基本聊天、私聊持久回复及记忆调度正常运行。
- 费用审查和生产证据见 [cost-audit-2026-09-10.md](cost-audit-2026-09-10.md)。根因是完整记忆文档的结构化输出至少 4341 token，超过原 4096 上限；R3 将记忆预算改为 16384 token、超时改为 240 秒，普通聊天保持 4096。余额不足下 40 秒观察窗为 0 次提取失败、0 次合并失败；窗口内 2 次 402 来自实时群聊模型请求。
