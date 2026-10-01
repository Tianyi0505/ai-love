# 数据库结构设计结果

**设计日期**：2026-08-26。**文档版本**：v2.2。本文记录当时的目标结构，现有结构快照见 [数据库字段](database-schema.md)，当前长期记忆能力见 [项目说明](../README.md)。

## 标识与数据归属

| 数据 | 目标结果 |
| --- | --- |
| AI 标识 | ai_ids 保存 ai_id 数值主键及唯一 ai_slug |
| 人物定义 | 配置来源提供显示名称、身份和运行属性 |
| 社交账号 | social_accounts 保存账号标识、平台标识、显示名及创建时间 |
| 账号唯一性 | account_id 与 (platform, platform_account_id) 具有唯一约束 |
| 账号绑定及关系 | ai_account_bindings、person_relationships、group_relationships 关联 ai_ids.ai_id |
| 表情素材 | stickers 保留持久数据，ai_id 可空，空值表示全局素材 |
| 联系人记忆 | person_memories 以 owner_ai_id 与 person_id 确定拥有者和主体 |
| 会话摘要 | conversation_summaries 以 (ai_id, conversation_id) 为主键 |
| 原始消息 | messages 保留 source_key 幂等键与来源资料 |
| 直播阵容与工具授权 | 配置对象定义运行范围与可用能力 |

## 目标字段

| 实体 | 字段 |
| --- | --- |
| ai_ids | ai_id、ai_slug、created_at、updated_at |
| social_accounts | social_account_id、account_id、platform、platform_account_id、display_name、created_at |
| person_memories | memory_id、owner_ai_id、person_id、memory_type、content、importance、confidence、source、lfu_state、created_at、updated_at、last_recalled_at、recall_count |
| conversation_summaries | ai_id、conversation_id、summary、message_count、started_at、ended_at、created_at、updated_at |
| messages | message_id、conversation_id、platform_identity_id、role、content、occurred_at、correlation_id、source_key、created_by_ai_id、expires_at |
| conversation_episodes | episode_id、ai_id、person_id、conversation_id、started_at、ended_at、summary、source_message_ids、created_at |

person_memories 的唯一键为 `(owner_ai_id, person_id, memory_type, content)`。Episode 的唯一键为 `(ai_id, person_id, conversation_id, started_at)`。消息 `expires_at` 空值表示永久保留，`created_by_ai_id` 表示 AI 主动消息归属。

联系人记忆索引包含 owner/person/importance 与 owner/type；会话摘要索引包含 ai_id/ended_at。数据访问采用 SQLAlchemy，结构迁移采用 Alembic，持久状态具有备份和恢复材料。

## QQ 空间游标

| Redis key | 类型 | 含义与保留期 |
| --- | --- | --- |
| qzone:cursor:{account_id}:{friend_uin} | String | 好友最新浏览时间戳，随好友关系长期保留 |
| qzone:commented:{account_id}:{friend_uin} | Set | 已评论 feed ID，保留 7 天 |

每个好友拥有独立游标，新增动态满足 `timestamp > cursor`；继续评论资格来自该好友对既有评论的回复。Redis 使用 AOF 与持久数据卷，游标的恢复结果由备份证据确认。

## 数据保障与设计指标

目标结构满足外键完整性、配置与身份映射一致性、消息来源唯一性和既有数据可恢复性。升级及恢复产物包含有效迁移、数据数量核验、配置快照和备份。

| 场景 | 设计目标 |
| --- | --- |
| 联系人记忆查询 | 小于 5 ms，缓存命中率 95% 以上 |
| 会话摘要查询 | 小于 10 ms，按时间范围检索 |
| AI 标识查询 | 小于 10 ms，注册表基数小于 100 行 |
| 存储占用 | 目标减少 30% 至 40% |

以上为设计指标，测量环境与实际结果由对应验收资料定义。

## 目标能力清单

- [ ] 联系人记忆与会话摘要具有明确查询接口及索引。
- [ ] QQ 空间好友游标具有独立持久状态。
- [ ] Elasticsearch、embedding 与 BM25 提供检索结果。
- [ ] 记忆重要度及 LFU 具有自动评分与时间衰减结果。
- [ ] 共享记忆采用显式授权的 owner 范围。
- [ ] 图片和音频记忆具有来源与摘要。
- [ ] 记忆保留策略具有确定的数据范围。
