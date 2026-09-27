# 数据模型与状态约束

沿用 `shared/database_models.py`、SQLAlchemy async 与 Alembic。当前迁移 head 为 `0005_lazy_lfu_state`，实施时复核是否有更新。新增以下 3 张专用表，不修改记忆、关系分值或身份映射。

## PrivateReplyJob（拟表 private_reply_jobs）

| 字段 | 含义 |
| --- | --- |
| job_id | 现有 Snowflake bigint 主键；数据库内接收顺序还需独立 received_seq，不能按平台时间排序 |
| received_seq | 数据库生成的接收序号，同会话以其升序处理 |
| ai_id / person_id / conversation_id | 可信归属；与既有实体关联 |
| platform / account_id / platform_message_id | 输入定位；与 conversation_id 构成平台事件唯一键，不包含可变化的 ai_id |
| run_id | 首次入站生成并持久保存，重投复用，唯一 |
| message_snapshot | JSONB，完整归一化 SocialMessage，含原始引用标记；增强后更新 |
| status | accepted / ready / processing / prepared / sent / failed / unknown |
| response_snapshot | 最终不可变 ResponseCommand，未生成前为空 |
| claim_version / lease_until | 领取版本与有限处理租约，防旧 worker 写入 |
| attempt_count / next_attempt_at | 有限恢复次数和下次可处理时间 |
| reason_code / created_at / updated_at / retain_until | 状态诊断与清理依据 |

约束：ai_id 固定为首次接受的归属；账号换绑后的旧事件重投沿用原任务，旧归属无法处理时暂停，不交给新 AI 重发。相同唯一输入键只创建一个任务、一个 run_id，并且只有首次创建可清零主动计数。索引覆盖 status + next_attempt_at 以及 conversation_id + received_seq。网络/模型调用不持有数据库行锁。

语音文件恢复降级为文字，仅允许在 SocialDelivery 尚未创建且未开始外发时原子更新 prepared Job；创建发送记录后不得以文件缺失为由修改既有摘要。

状态：accepted 在 Gateway 补充上下文后 ready；Agent 领取后 processing；最终内容保存为 prepared；发送确认后 sent，明确不可恢复失败为 failed，送达不确定为 unknown。已生成内容优先重用；processing 中断且可能已调用工具时只生成无工具故障说明，不重放整轮。

租约到期只允许新 claim_version 的处理者提交。Gateway 在首次 prepared→sending 时验证源 job_id / claim_version 或已持久最终内容的归属；旧 worker 不能在恢复者提交后发送另一个结果。sent/failed/unknown 不进入普通自动领取；unknown 后续用户私信仍正常处理。

## PrivateContactState（拟表 private_contact_states）

| 字段 | 含义 |
| --- | --- |
| ai_id + person_id | 联合主键，与账号路由分离 |
| unanswered_count | 已确认未获回复的主动次数，范围 0..3 |
| last_success_at | 最近成功主动联系时间，用户回复不会抹掉冷却依据 |
| last_inbound_job_id | 最近首次接收的有效私信，用于追踪清零依据 |
| revision | 新私信或预占变化时递增，用于识别交错 |
| pending_run_id / pending_revision | 唯一预占发送和当时版本 |
| status | active / suspended / unknown |
| reason_code / updated_at | 迁移暂停、状态缺失、未知结果等原因 |

- 新可信建立的联系人显式创建 active/0；升级时已有联系人建 suspended，不可因缺行或 TTL 自动初始化为 0。
- 首次入站事务同时插入 Job、锁定状态行、计数清零并记录该 job。重投不触发重置。群消息不调用该事务。
- 对无 pending 的 active 状态，满足间隔且 count<3 才能预占。预占发生在生成后、发送前；存在预占即阻止第二个主动发送。
- prepared 尚未开始外发时有新私信：取消旧预占，保留 count=0。新主动生成必须基于新版本与安静期重新评估。
- 无交错的 sent：count+1，更新 last_success_at，释放 pending；明确未发送 failed：释放 pending，不增加计数。
- sending 与新私信交错：记录清零，但 pending 保留；若无法证明实际发送相对私信的顺序，status=unknown 并保留凭证，禁止猜测最终计数。核实后按已证实顺序提交；收到新私信仍保证被动回复。
- 无响应/崩溃残留 sending：保留 pending、unknown，不因超时或下一次新私信自动释放待核实发送。新私信重置计数不等于解除所有发送风险。

## SocialDelivery（拟表 social_deliveries）

| 字段 | 含义 |
| --- | --- |
| ai_id + account_id + run_id | 唯一发送键，客户端恢复时保持不变 |
| kind | private_reply / proactive_private；本次仅这两类启用新可靠状态 |
| source_job_id / claim_version | 被动回复归属；主动时为空，由 pending_run_id 验证预占 |
| person_id / conversation_id | 目标实体和会话 |
| request_snapshot / request_digest | 不可变目标及最终内容、完整性摘要 |
| status | prepared / sending / sent / failed / unknown |
| platform_message_id | 权威平台确认编号，未确认时为空 |
| attempt_count / reason_code / history_recorded | 安全重试与会话历史补记 |
| created_at / updated_at | 状态时间，不能用 ACK 时间冒充实际平台发送顺序 |

Gateway 先提交 sending 才调用平台；竞争者读取已有状态。sent 返回同一 message_id，failed 仅在可证明未发且可重试时复用原内容有限尝试。不同内容/目标复用键拒绝。发送成功后先存 sent，再补历史，补历史失败不再外发。

创建发送记录时校验来源；实际 prepared→sending 必须在同一事务锁定发送记录及来源 Job/ContactState，再校验有效领取版本/主动预占。入站取消预占与该切换共享行锁，不能用创建时的过期校验替代发送前校验。引用明确被拒且确认未发送的单次普通回复降级是唯一允许的受控 request_snapshot 修订，记录 revision 和原因；其余内容变化必须拒绝。unknown 禁止该降级。

## 清理、恢复与迁移

正文快照沿用现有 message_retention_days=180 的保留规则，不新增永久私聊正文。到期可清除正文，但保留无正文输入唯一键、run_id 和终态的最小去重凭据；未解决 unknown 保留必要定位信息并告警。主动计数不设 TTL，普通清理不删除。

事务同时管理首次入站和清零；Gateway 与 Agent 共享既有数据库会话工厂注入专用仓库。数据库不可用时不发主动、不声称接收成功；依赖恢复后的扫描只重做安全阶段。

升级增加表/索引并为已有可信联系人建 suspended；不导入不可靠的历史主动次数。旧 Redis 保留以免影响群聊。回滚应用时保留新表与未知记录，主动关闭；不以删表、清库或重置人物关系恢复额度。

