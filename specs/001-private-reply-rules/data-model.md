# 私聊状态数据模型

SQLAlchemy async 与 Alembic 提供持久实体和结构结果，三个业务实体分别拥有输入、联系额度和平台发送状态。

## PrivateReplyJob — private_reply_jobs

| 字段 | 含义 |
| --- | --- |
| job_id / received_seq | 稳定主键及数据库接收序号 |
| ai_id / person_id / conversation_id | 首次输入的可信归属 |
| platform / account_id / platform_message_id | 输入定位，与 conversation_id 组成唯一键 |
| run_id | 首次持久生成的唯一回应标识 |
| message_snapshot | 完整 SocialMessage 与原始引用事实 |
| status | accepted / ready / processing / prepared / sent / failed / unknown |
| response_snapshot | 已确定的最终 ResponseCommand |
| claim_version / lease_until | 有效领取版本与处理租约 |
| attempt_count / next_attempt_at | 有限恢复预算 |
| reason_code / created_at / updated_at / retain_until | 状态定位与保留期 |

同一平台事件返回原 job、ai_id 和 run_id，首次创建对应唯一联系清零依据。索引包含 status/next_attempt_at、conversation_id/received_seq。有效提交者与发送者具有当前 claim_version。网络及模型调用的执行范围为短事务之外。

语音快照的文字降级资格为 prepared 且发送记录尚处创建资格窗口，最终发送摘要具有固定来源。终态对应持久结果，新私信具有独立任务资格。

## PrivateContactState — private_contact_states

| 字段 | 含义 |
| --- | --- |
| ai_id + person_id | 联系额度联合主键 |
| unanswered_count | 当前联系轮次的成功计数，0..3 |
| last_success_at | 最近成功主动时间与冷却依据 |
| last_inbound_job_id / last_inbound_at | 新有效私信的清零依据 |
| revision | 联系状态修订 |
| pending_run_id / pending_revision | 唯一主动预占与对应轮次 |
| status | active / suspended / unknown |
| reason_code / updated_at | 状态原因与更新时间 |

历史联系人以 suspended/migration 保持保守初始化，可信新联系人具有 active/0 依据。首次有效私信事务建立新轮次，重复事件保持原修订。active、计数小于 3、冷却及安静期满足时具有预占资格。

平台 sent 结果对应唯一计数提交，failed 的额度结果取决于确定送达依据，sending/unknown 的预占保留定位凭证。轮次交错依据已证明事件顺序；新的被动回应具有独立资格。额度随持久联系状态保留。

## SocialDelivery — social_deliveries

| 字段 | 含义 |
| --- | --- |
| ai_id + account_id + run_id | 唯一发送键 |
| kind | private_reply / proactive_private |
| source_job_id / claim_version | 被动来源与有效领取版本 |
| person_id / conversation_id | 目标归属 |
| request_snapshot / request_digest | 固定目标、内容与摘要 |
| status | prepared / sending / sent / failed / unknown |
| platform_message_id | 权威平台确认 |
| attempt_count / reason_code / history_recorded | 恢复预算、原因与历史凭证 |
| created_at / updated_at | 记录时间 |

sending 资格由同一事务的发送记录与来源状态锁确定。重复 sent 返回原 message_id，历史补记依据原确认。目标或内容差异对应 conflict 状态。引用降级资格具有平台确定结果，同一 run_id 的受控快照修订保留原因和摘要。

## 保留与恢复

正文快照采用 180 天保留期，输入唯一键、run_id、终态和主动额度保留。unknown 保留核实资料。迁移及应用恢复结果保留人物、关系、记忆、群聊缓存和三张状态表。
