# 私聊状态运维结果标准

Gateway 与 ai-agent 使用匹配 RPC 版本。结构版本为 `0006_private_reply_state`，三张持久表为 private_reply_jobs、private_contact_states、social_deliveries。升级与恢复结果保留人物、关系、消息和记忆数据，历史联系人具有 suspended/migration 初始化状态。

## 状态查询

```sql
SELECT status, count(*) AS jobs, min(created_at) AS oldest
FROM private_reply_jobs
GROUP BY status
ORDER BY status;

SELECT status, count(*) AS deliveries, min(updated_at) AS oldest
FROM social_deliveries
GROUP BY status
ORDER BY status;

SELECT ai_id, person_id, unanswered_count, status, reason_code,
       pending_run_id, last_success_at, last_inbound_at
FROM private_contact_states
WHERE status <> 'active' OR unanswered_count >= 3
ORDER BY updated_at;
```

查询范围为状态与定位字段。sending 超过 60 秒对应 unknown 核实状态；平台权威 message_id 或等价凭证是送达判定依据。恢复资格采用原 run_id、原快照及确定状态。新的有效私信具有独立回应任务。

## 告警结果

| 信号 | 条件 | 日志事件 |
| --- | --- | --- |
| ailove.private_reply.oldest_pending_seconds | 大于 60 秒 | private_reply_pending_alert |
| ailove.private_reply.result{status=unknown} | 任意一次 | private_reply_unknown |
| 连续状态结果 | 连续 3 次 failed/unknown | private_reply_failure_streak |
| ailove.private_reply.scan_failures | 任意一次 | private_reply_scan_failed |

指标标签由固定状态和原因码组成，日志采用脱敏定位资料。实际通知来源为集群监测系统，Jaeger 监测端口为 8888。

## 恢复与保留

核实资料关联 Gateway、PostgreSQL、NATS、NapCat 的健康状态、发送键与 source_job_id。成功状态依据权威平台凭证，安全重入资格依据确定发送结果，unknown 保留核实资料与联系预占。

隔离恢复数据库的名称以 `_test` 结尾。恢复结果核对三张状态表、关系数量及 alembic_version。可能落后的额度状态具有 suspended/unknown 标记。应用恢复保留新增表、任务、额度及平台凭证。

180 天正文保留期适用于终结任务和已补写历史的快照；最小去重键、终态、平台编号、额度及 unknown 定位资料持续保留。

## 成本依据

普通文本样本每条至多一次 generate_plan，文字兜底的额外模型调用数为 0。实际费用等于各模型输入/输出 token 与对应使用时单价的加权总和，费用证据采用账单和真实用量。
