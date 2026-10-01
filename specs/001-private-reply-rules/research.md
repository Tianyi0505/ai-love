# 私聊可靠回应设计依据

**日期**：2026-09-10。证据类型为本地调用链静态核对，运行验收见 [validation.md](validation.md)。

| 设计决策 | 依据与结果 |
| --- | --- |
| 私聊固定回应资格 | Persona 的 private 判断与 AIRuntime 会话协调提供明确入口 |
| PostgreSQL 权威任务 | 固定快照、输入唯一键和扫描结果具有重启恢复依据 |
| NATS 唤醒 | 现有主题提供及时处理入口，数据库扫描提供恢复依据 |
| 专用联系状态 | ai_id + person_id、0..3 计数和持久轮次对应主动额度 |
| 完整可信身份 | account/user/person 来自当前 AI 绑定的同一身份记录 |
| 固定发送键 | run_id、目标、摘要和平台确认提供唯一投递结果 |
| unknown | 核实状态保留发送凭证及联系预占 |
| 当前引用目标 | 原始引用标记与 quote_ref 保留 B，reply_to_message_id 对应 A |
| 历史初始化 | 旧联系人 suspended，新有效私信具有 active/0 依据 |
| 调度条件 | 30 分钟冷却、6 小时静默及工作作息各有独立意义 |

状态仓库位于 shared，平台适配位于 Channel，回应与联系决策位于 Agent，群聊缓存保留原 SessionManager 语义。模型费用依据实际单价与 token，性能依据独立环境的测量结果。
