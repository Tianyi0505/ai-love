# 私聊可靠回复运维手册

## 协同升级

Gateway 与 ai-agent 必须使用同一版本。新 `SocialSendRequest` 字段受 `extra=forbid` 约束，不能让新 Agent 向旧 Gateway 发送可靠私聊请求。

1. 关闭主动私聊，并暂停 QQ 入站。
2. 备份 PostgreSQL，记录 `alembic_version`。
3. 执行 `python -m alembic upgrade 0006_private_reply_state`。
4. 先启动 Gateway，确认 `social.send.status.request` 已注册，再启动 ai-agent。
5. 检查旧联系人均为 `suspended/migration`，新有效私信可将对应联系人转为 `active`。
6. 完成本地替身验证后再恢复入口。真实部署和真实 QQ 发信需要单独授权。

新增迁移会保留人物、关系、消息和记忆数据。首次全新建库也可从 `0001` 升到 head；`0006` 使用 `IF NOT EXISTS` 兼容仓库早期迁移会读取当前 ORM 元数据的既有行为。

## 只读状态检查

以下查询不包含消息正文，适合先判断是否可自动恢复：

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

`sending` 超过 60 秒会在恢复扫描中转为 `unknown`；没有平台权威 `message_id` 或等价凭证时，不得把它改成未发送、释放主动额度或更换 `run_id` 重发。收到新的有效私信仍会生成独立被动回复。

## 告警信号

应用通过 OpenTelemetry 指标和无正文结构化日志暴露以下信号；Kubernetes 已部署现有 Jaeger 资源并开放其 8888 监测端口。

| 信号 | 告警条件 | 日志事件 |
| --- | --- | --- |
| `ailove.private_reply.oldest_pending_seconds` | 大于 60 秒 | `private_reply_pending_alert` |
| `ailove.private_reply.result{status=unknown}` | 任意一次 | `private_reply_unknown` |
| 连续失败 | 连续 3 次 `failed/unknown` | `private_reply_failure_streak` |
| `ailove.private_reply.scan_failures` | 任意一次 | `private_reply_scan_failed` |

指标标签只允许固定状态和原因码；异常正文、用户消息、凭据与授权头不会进入指标或上述告警日志。实际通知渠道由集群已有监控系统订阅这些信号，本次没有向外部服务写入告警配置。

## unknown 排查

1. 核对 Gateway、PostgreSQL、NATS 和 NapCat 的健康状态及时间范围。
2. 用 `(ai_id, account_id, run_id)` 查询 `social_deliveries`，再按 `source_job_id` 关联私信任务。
3. 在 NapCat 或平台侧取得权威消息编号；本地缺少 outbound 历史不能证明消息未发送。
4. 有权威成功凭证时按运维变更流程补记成功；有权威未发送凭证时才允许使用原 `run_id` 和原快照恢复。
5. 无法证明结果时保持 `unknown`，继续允许新的被动私信任务。

## 备份恢复与回滚

恢复演练必须使用名称以 `_test` 结尾的隔离数据库。恢复后核对三张状态表、旧关系行数和 `alembic_version`；若备份时间点可能漏掉已发送的主动消息，将相关联系人保持 `unknown/suspended`。

应用回滚时关闭主动私聊和新私信领取，导出非终态任务与 `unknown` 发送清单，然后回滚 Gateway 与 Agent。保留 `private_reply_jobs`、`private_contact_states`、`social_deliveries` 三张表；迁移的 `downgrade()` 会主动拒绝破坏性删除。旧应用不提供本特性的保证。

180 天后只清理已终结任务和已补写历史发送的正文快照；唯一去重键、状态、平台消息编号和主动计数继续保留。`unknown` 的定位快照不会自动清理。

## 成本上线表

本地普通文本样本保持每条最多一次 `generate_plan`，兜底不调用模型。上线前填写实际提供方账单口径：

| 模型 | 输入单价 | 输出单价 | 实际输入 tokens | 实际输出 tokens | 估算费用 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 当前主模型 | 待提供 | 待提供 | 待采集 | 待采集 | 不计算 | 未验收 |
| 故障切换模型 | 待提供 | 待提供 | 待采集 | 待采集 | 不计算 | 未验收 |

没有实际单价和 token 量时，不能声称货币成本已经验收。
