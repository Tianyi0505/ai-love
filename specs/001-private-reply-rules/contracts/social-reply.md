# 社交回应接口契约

本契约描述已实现的 Gateway/Agent 接口调整。实现沿用 Pydantic RpcModel、NATS request/reply 和现有错误 envelope，不新增 HTTP 服务。

## 入站 SocialMessage

继续使用 `social.chat.{ai_id}`。私信新增元数据 `private_reply_job_id`；run_id 从持久首次入站记录取得。消费者依据该 job 领取，不能只凭收到事件立即再次生成。

保留 `meta.reply_message_id` 作为原始历史引用 B 的编号（hydrate 不再消费删除），`quote_ref` 为可选补全结果。带引用的判据为原始引用标记或已有 quote_ref，正常回应目标为当前 message_id=A。原始 B 只用于上下文，不转作出站引用。

无引用消息、群复读和主动私聊继续不自动加引用。群聊沿用现有消费路径；新的私信恢复扫描仅查询私信任务。

## social.send.request

保留 SocialSendRequest 原有字段：ai_id、account_id、conversation_id、channel、chat、type、text、run_id、reply_to_message_id、repeat_message_id、sticker、voice。

新增可选字段：

| 字段 | 类型 / 默认 | 语义 |
| --- | --- | --- |
| delivery_kind | string / 空 | private_reply 或 proactive_private；空值维持既有非私信路径 |
| source_job_id | string / 空 | 私信持久任务，来自运行时可信上下文 |
| claim_version | integer / 0 | 私信任务领取版本，非模型填写 |
| person_id | string / 空 | 用于主动预占校验，来自可信身份 |

Gateway 在 prepared→sending 的同一数据库事务中锁定并验证来源任务领取版本或主动预占，失效则不外发。AgentExecutionContext / ResponseCommand 必须透传必要字段。私信路径必须提供固定 run_id 和对应来源；Gateway 不信任模型指定的账号、人物或目标，核对任务快照/主动预占及账号归属。既有非私信路径不被强制新增去重语义。

入站平台事件去重不包含 ai_id；账号换绑不能为旧事件产生新任务，首次归属保持不变。发送键为 (ai_id, account_id, run_id)。相同键不同内容或目标返回明确冲突；sending/unknown 返回状态错误且不得外发；已 sent 返回既有结果。使用已知未发送的“引用不可用”错误降级时，Gateway 在同一操作下记录一次受控引用移除，调用方不能任意修改文本。

成功响应保持 `{ "message_id": "平台编号" }`，避免把“正在发送”伪装成功。

新增明确 RPC 错误码：

- DeliveryInProgress：存在进行中发送，查询结果，不再次发。
- DeliveryUnknown：无法确认送达，暂停自动恢复并告警。
- DeliveryConflict：相同键内容或目标不同，终止。
- DeliveryRejected：已知未发送的永久拒绝，终止。
- DeliveryRetryable：可证明未发送的暂时失败，仅允许预算内重试。
- StaleClaim：任务版本或主动预占已失效，不外发。

现有 RpcEnvelope 的 error.code 必须显式保留这些分类，不能把所有底层异常统一当作可重试。HTTP 超时和无确认的连接断开默认 Unknown。

## social.send.status.request（新增，只读）

请求：ai_id、account_id、run_id，均为必填字符串。

响应：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| status | string | not_found / prepared / sending / sent / failed / unknown |
| message_id | string | 仅已确认时提供 |
| reason_code | string | 无正文的诊断原因 |
| retryable | bool | 只有明确未发送且允许恢复才为 true |

查询仅允许当前可信账号作用域，不按任意人物浏览发送记录。Agent RPC 超时后先查询，sent 时提交成功；not_found 并不证明旧请求永远不会到达，只能使用同一 run_id 重入去重处理，不能换号发送。sending/unknown 保持暂停。

状态查询不得自动调用 send；QQ 缺少权威凭据时返回 unknown，不根据本地时间或缺少 Message 行猜测。

## 配置契约

- `behavior_policy.private_reply` 当前为 always；有效私聊必回复固定执行。未来其他值不得静默降低此保证；本次不增参与判断开关。
- `proactive.private_cooldown_sec` 默认 1800，复用原字段；`private_interval_sec=1800`、`private_quiet_period_sec=21600` 和 work_hours 保留。
- 未获回复上限固定 3，不增可放宽配置。
- 无模型兜底文本进入现有提示/消息配置，区分无法理解、模型不可用、处理被中断。
- 恢复扫描间隔 5 秒、批次 100、会话并发 10、处理预算 45 秒、领取租约 120 秒、心跳 15 秒、明确未发恢复最多 2 次，归属现有服务配置；只做正数与必要时间关系校验。

## 版本与兼容

RpcModel 当前 extra=forbid，新字段不能直接发送到旧 Gateway。此次要求 Gateway 与 Agent 协同版本升级：暂停入口、迁移、部署、校验后恢复。新增查询主题必须先注册再启用客户端恢复。不得改动白名单内容或 NapCat 登录态。

