# 社交回应接口契约

接口采用 Pydantic RpcModel、NATS request/reply 与现有错误 envelope。

## 入站 SocialMessage

主题为 `social.chat.{ai_id}`。私信元数据 `private_reply_job_id` 对应持久任务，run_id 对应首次入站记录，处理资格由有效领取版本确定。

`meta.reply_message_id` 保留历史 B 的编号，`quote_ref` 保留可用的历史内容。带引用消息的出站目标为当前 message_id=A。普通输入、群复读和主动私聊采用各自既有展示语义。

## social.send.request

原字段为 ai_id、account_id、conversation_id、channel、chat、type、text、run_id、reply_to_message_id、repeat_message_id、sticker、voice。

| 扩展字段 | 类型与默认 | 语义 |
| --- | --- | --- |
| delivery_kind | string / 空 | private_reply 或 proactive_private，空值对应既有路径 |
| source_job_id | string / 空 | 可信运行时任务 |
| claim_version | integer / 0 | 有效任务领取版本 |
| person_id | string / 空 | 可信联系预占归属 |

发送资格包含可信身份、账号绑定、任务快照或主动预占，在 prepared/sending 事务边界形成一致结果。平台事件的首次归属保留，发送键为 `(ai_id, account_id, run_id)`。相同请求返回已有结果，目标与内容差异对应明确 conflict。

成功响应为 `{ "message_id": "平台编号" }`。RPC 状态码如下：

| 状态码 | 结果语义 |
| --- | --- |
| DeliveryInProgress | 进行中状态及原结果查询入口 |
| DeliveryUnknown | 核实状态、定位凭证和告警 |
| DeliveryConflict | 固定键的请求差异 |
| DeliveryRejected | 平台确定结果及结束状态 |
| DeliveryRetryable | 确定安全的有限恢复资格 |
| StaleClaim | 当前任务或预占版本要求 |

`error.code` 保留各状态分类，HTTP 超时与连接确认状态以实际凭证为依据。

## social.send.status.request

请求字段 ai_id、account_id、run_id 为必填字符串，查询范围为当前可信账号。

| 响应字段 | 类型 | 语义 |
| --- | --- | --- |
| status | string | not_found / prepared / sending / sent / failed / unknown |
| message_id | string | 权威确认编号 |
| reason_code | string | 脱敏原因 |
| retryable | bool | 安全状态及恢复预算决定的资格 |

查询提供已有记录，恢复使用同一 run_id 和同一内容。sending/unknown 的结果由核实依据确定。

## 配置契约

| 配置 | 值 |
| --- | --- |
| behavior_policy.private_reply | always |
| proactive.private_cooldown_sec | 1800 |
| proactive.private_interval_sec | 1800 |
| proactive.private_quiet_period_sec | 21600 |
| 主动轮次额度 | 3 |
| 扫描间隔 / 批次 / 并发 | 5 秒 / 100 / 10 |
| 处理预算 / 租约 / 心跳 | 45 秒 / 120 秒 / 15 秒 |
| 安全恢复 | 最多 2 次 |

兜底文案表达内容理解、模型和处理状态。Gateway 与 Agent 使用同一 RPC 版本及 extra=forbid，状态查询入口具有注册结果。既有白名单与 NapCat 登录态保留。
