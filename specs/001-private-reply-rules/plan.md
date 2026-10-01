# Implementation Plan: 私聊可靠回应设计结果

**Branch**: main | **Date**: 2026-09-10 | **Spec**: [spec.md](spec.md)

## Summary

可靠私信具有持久接收、稳定去重、有序回应和发送凭证；主动联系具有每轮 3 次额度、30 分钟冷却和可信清零依据；引用回复指向当前消息。

## Technical Context

| 项目 | 设计结果 |
| --- | --- |
| 语言与依赖 | Python 3.11、现有 SQLAlchemy async、asyncpg、Alembic、Pydantic、NATS、Redis、httpx、LangChain |
| 持久状态 | PostgreSQL 中的 private_reply_jobs、private_contact_states、social_deliveries |
| 会话缓存 | Redis SessionManager 继续承载群聊临时状态 |
| 运行边界 | Gateway、ai-agent 与进程内 Memory |
| 唤醒与恢复 | 既有 NATS 主题与 5 秒扫描，数据库任务为权威来源 |
| 样本与指标 | 10 会话、每秒 1 条、600 条，P95 ≤10 秒，覆盖率 100% |
| 状态恢复 | 已确认状态普通重启 RPO=0，安全任务恢复目标为 60 秒 |

## Constitution Check

| 原则 | 结果要求 |
| --- | --- |
| 持续身份 | 人物、长期记忆与关系内容保持连续 |
| 依据与幂等 | 首次输入、关系副作用和记忆活动具有稳定归属 |
| 场景与受众 | 当前目标与历史引用分离，人物额度独立 |
| 反馈 | prepared、sending、sent、failed、unknown 对应真实状态 |
| 架构 | 平台协议归 Channel，回应与联系决策归 Agent，状态归专用仓库 |
| 验收 | 平台入口至发送结果、真实数据库竞争与恢复具有证据 |

## 状态与预算

首次输入唯一键由平台、账号、会话和消息编号组成，首次 ai_id 与 run_id 保留。新任务及联系计数重置位于同一事务，重复输入返回原任务。输入快照包含原始引用标记。

同会话以 received_seq 有序领取，claim_version 确定有效处理者。扫描批次 100，会话并发 10，处理预算 45 秒，租约 120 秒，心跳 15 秒。已持久内容及 run_id 是恢复依据，工具副作用具有独立确认状态。

发送唯一键为 `(ai_id, account_id, run_id)`，目标和内容摘要固定。平台确认对应 sent 与 message_id；unknown 对应核实状态；安全恢复资格以确定发送状态和预算为依据，重试最多 2 次，间隔为 5、15 秒。

主动状态按 AI/person 持久保存，成功额度为 0..3。身份路由的 account/user/person 来自同一可信记录。唯一预占和发送资格对应当前轮次与版本，平台确认决定计数，新的有效私信具有独立被动回应。

## 交付与恢复结果

迁移 `0006_private_reply_state` 提供三张状态表与索引。历史联系人初始状态为 suspended/migration，可信新联系人及新有效私信具有明确初始化依据。原关系、记忆、消息及群聊缓存保留。

Gateway 与 Agent 处于匹配版本，RPC 采用 extra=forbid。发布结果具备数据库备份、迁移 head、配置校验及验收资料。应用恢复保留三张状态表、主动额度与 unknown 凭证。

正文快照保留期为 180 天，最小去重键、终态、平台编号与额度保持可用。结构化指标包含 pending、回应覆盖、fallback、unknown、发送状态和调用量，标签采用固定状态与原因码。

具体字段见 [data-model.md](data-model.md)，接口见 [contracts/social-reply.md](contracts/social-reply.md)，交付证据见 [validation.md](validation.md)。
