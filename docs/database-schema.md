# 数据库表结构文档

> 生成时间：2026-08-26
> 数据库：PostgreSQL + pgvector 扩展
> ORM：SQLAlchemy 2.0
> 迁移工具：Alembic

## 目录

1. [AI 与账号管理](#1-ai-与账号管理)
2. [社交与身份](#2-社交与身份)
3. [会话与消息](#3-会话与消息)
4. [记忆系统](#4-记忆系统)
5. [直播管理](#5-直播管理)
6. [扩展与工具](#6-扩展与工具)
7. [运营与审计](#7-运营与审计)

---

## 1. AI 与账号管理

### ai_profiles

AI 档案记录表

| 字段名                | 类型                 | 约束                          | 说明                   |
| ------------------ | ------------------ | --------------------------- | -------------------- |
| profile_id         | BigInteger         | PK, 自增                      | 档案ID                 |
| ai_id              | Text               | NOT NULL, UNIQUE            | AI实例ID               |
| definition_version | Integer            | NOT NULL                    | 定义版本号                |
| status             | Text               | NOT NULL                    | 状态（active/inactive等） |
| model_profile_id   | Text               | NOT NULL, DEFAULT 'default' | 模型档案ID               |
| voice_profile_id   | Text               | NOT NULL, DEFAULT 'default' | 语音档案ID               |
| avatar_profile_id  | Text               | NOT NULL, DEFAULT 'default' | 头像档案ID               |
| updated_at         | DateTime(timezone) | NOT NULL, DEFAULT now()     | 更新时间                 |

**索引：**

- 主键：`profile_id`
- 唯一约束：`ai_id`

---

### social_accounts

社交平台账号表

| 字段名                 | 类型                 | 约束                          | 说明                 |
| ------------------- | ------------------ | --------------------------- | ------------------ |
| social_account_id   | BigInteger         | PK, 自增                      | 账号ID               |
| account_id          | Text               | NOT NULL, UNIQUE            | 内部账号标识             |
| platform            | Text               | NOT NULL                    | 平台名称（如 qq/wechat）  |
| platform_account_id | Text               | NOT NULL                    | 平台侧账号ID            |
| display_name        | Text               | NOT NULL, DEFAULT ''        | 显示名称               |
| credential_ref      | Text               | NOT NULL, DEFAULT ''        | 凭据引用（Nacos配置key）   |
| status              | Text               | NOT NULL, DEFAULT 'offline' | 状态（online/offline） |
| is_live_platform    | Boolean            | NOT NULL, DEFAULT false     | 是否支持直播             |
| allows_multi_ai     | Boolean            | NOT NULL, DEFAULT false     | 是否允许多AI绑定          |
| created_at          | DateTime(timezone) | NOT NULL, DEFAULT now()     | 创建时间               |

**索引：**

- 主键：`social_account_id`
- 唯一约束：`account_id`
- 唯一约束：`(platform, platform_account_id)`

---

### ai_account_bindings

AI与账号绑定表

| 字段名        | 类型                 | 约束                      | 说明     |
| ---------- | ------------------ | ----------------------- | ------ |
| binding_id | BigInteger         | PK, 自增                  | 绑定ID   |
| account_id | Text               | NOT NULL                | 账号ID   |
| ai_id      | Text               | NOT NULL                | AI实例ID |
| bound_at   | DateTime(timezone) | NOT NULL, DEFAULT now() | 绑定时间   |
| ended_at   | DateTime(timezone) | NULLABLE                | 解绑时间   |

**索引：**

- 主键：`binding_id`

---

### model_profiles

模型配置档案表

| 字段名                     | 类型                 | 约束                      | 说明             |
| ----------------------- | ------------------ | ----------------------- | -------------- |
| model_profile_record_id | BigInteger         | PK, 自增                  | 记录ID           |
| model_profile_id        | Text               | NOT NULL, UNIQUE        | 档案ID           |
| config                  | JSONB              | NOT NULL                | 配置内容（模型参数/路由等） |
| updated_at              | DateTime(timezone) | NOT NULL, DEFAULT now() | 更新时间           |

**索引：**

- 主键：`model_profile_record_id`
- 唯一约束：`model_profile_id`

---

## 2. 社交与身份

### persons

人物表

| 字段名          | 类型                 | 约束                      | 说明   |
| ------------ | ------------------ | ----------------------- | ---- |
| person_id    | BigInteger         | PK, 自增                  | 人物ID |
| display_name | Text               | NOT NULL, DEFAULT ''    | 显示名称 |
| created_at   | DateTime(timezone) | NOT NULL, DEFAULT now() | 创建时间 |

**索引：**

- 主键：`person_id`

---

### platform_identities

平台身份表（一个人物可对应多个平台账号）

| 字段名              | 类型                 | 约束                      | 说明                           |
| ---------------- | ------------------ | ----------------------- | ---------------------------- |
| identity_id      | BigInteger         | PK, 自增                  | 身份ID                         |
| person_id        | BigInteger         | NOT NULL                | 人物ID（FK → persons.person_id） |
| platform         | Text               | NOT NULL                | 平台名称                         |
| account_id       | Text               | NOT NULL                | 账号ID                         |
| platform_user_id | Text               | NOT NULL                | 平台用户ID                       |
| verified_by      | Text               | NOT NULL                | 验证方式（manual/auto等）           |
| verified_at      | DateTime(timezone) | NOT NULL, DEFAULT now() | 验证时间                         |

**索引：**

- 主键：`identity_id`
- 唯一约束：`(platform, account_id, platform_user_id)`

---

### group_members

群成员表

| 字段名              | 类型                 | 约束                         | 说明                           |
| ---------------- | ------------------ | -------------------------- | ---------------------------- |
| group_member_id  | BigInteger         | PK, 自增                     | 成员ID                         |
| platform         | Text               | NOT NULL                   | 平台名称                         |
| account_id       | Text               | NOT NULL                   | 账号ID                         |
| chat_id          | Text               | NOT NULL                   | 群ID                          |
| platform_user_id | Text               | NOT NULL                   | 平台用户ID                       |
| person_id        | BigInteger         | NOT NULL                   | 人物ID（FK → persons.person_id） |
| nickname         | Text               | NOT NULL, DEFAULT ''       | 昵称                           |
| group_card       | Text               | NOT NULL, DEFAULT ''       | 群名片                          |
| role             | Text               | NOT NULL, DEFAULT 'member' | 角色（owner/admin/member）       |
| is_active        | Boolean            | NOT NULL, DEFAULT true     | 是否活跃                         |
| last_seen_at     | DateTime(timezone) | NOT NULL, DEFAULT now()    | 最后在线时间                       |

**索引：**

- 主键：`group_member_id`
- 唯一约束：`(platform, account_id, chat_id, platform_user_id)`
- 索引：`idx_group_members_scope_role` (platform, account_id, chat_id, role) WHERE is_active
- 索引：`idx_group_members_person` (person_id, last_seen_at DESC)

---

### person_relationships

人物关系表（AI对某个人的关系评估）

| 字段名                    | 类型                 | 约束                     | 说明                           |
| ---------------------- | ------------------ | ---------------------- | ---------------------------- |
| person_relationship_id | BigInteger         | PK, 自增                 | 关系ID                         |
| ai_id                  | Text               | NOT NULL               | AI实例ID                       |
| person_id              | BigInteger         | NOT NULL               | 人物ID（FK → persons.person_id） |
| familiarity            | Float              | NOT NULL, DEFAULT 0    | 熟悉度（0-1）                     |
| affinity               | Float              | NOT NULL, DEFAULT 0    | 好感度（0-1）                     |
| trust                  | Float              | NOT NULL, DEFAULT 0    | 信任度（0-1）                     |
| importance             | Float              | NOT NULL, DEFAULT 0    | 重要度（0-1）                     |
| lfu_state              | JSONB              | NOT NULL, DEFAULT '{}' | LFU状态（访问频率衰减）                |
| ceiling_policy         | Text               | NOT NULL               | 上限策略（受限/正常/亲密）               |
| last_interaction_at    | DateTime(timezone) | NULLABLE               | 最后互动时间                       |

**索引：**

- 主键：`person_relationship_id`
- 唯一约束：`(ai_id, person_id)`

---

### group_relationships

群关系表（AI对某个群的关系评估）

| 字段名                   | 类型                 | 约束                     | 说明        |
| --------------------- | ------------------ | ---------------------- | --------- |
| group_relationship_id | BigInteger         | PK, 自增                 | 关系ID      |
| ai_id                 | Text               | NOT NULL               | AI实例ID    |
| account_id            | Text               | NOT NULL               | 账号ID      |
| platform_group_id     | Text               | NOT NULL               | 平台群ID     |
| familiarity           | Float              | NOT NULL, DEFAULT 0    | 熟悉度（0-1）  |
| belonging             | Float              | NOT NULL, DEFAULT 0    | 归属感（0-1）  |
| affinity              | Float              | NOT NULL, DEFAULT 0    | 好感度（0-1）  |
| activity_willingness  | Float              | NOT NULL, DEFAULT 0    | 活跃意愿（0-1） |
| lfu_state             | JSONB              | NOT NULL, DEFAULT '{}' | LFU状态     |
| ceiling_policy        | Text               | NOT NULL               | 上限策略      |
| last_interaction_at   | DateTime(timezone) | NULLABLE               | 最后互动时间    |

**索引：**

- 主键：`group_relationship_id`
- 唯一约束：`(ai_id, account_id, platform_group_id)`

---

### person_mentions

群内称呼证据表（记录谁被如何称呼）

| 字段名                | 类型                 | 约束                      | 说明                                       |
| ------------------ | ------------------ | ----------------------- | ---------------------------------------- |
| mention_id         | BigInteger         | PK, 自增                  | 称呼ID                                     |
| mention_text       | Text               | NOT NULL                | 原始称呼文本                                   |
| normalized_mention | Text               | NOT NULL                | 归一化称呼（小写/去符号等）                           |
| person_id          | BigInteger         | NOT NULL                | 人物ID（FK → persons.person_id）             |
| scope_type         | Text               | NOT NULL                | 范围类型（group/private）                      |
| scope_id           | Text               | NOT NULL, DEFAULT ''    | 范围ID（群ID/会话ID）                           |
| conversation_id    | BigInteger         | NULLABLE                | 会话ID（FK → conversations.conversation_id） |
| source_message_id  | Text               | NOT NULL, DEFAULT ''    | 来源消息ID                                   |
| evidence_type      | Text               | NOT NULL                | 证据类型（at/mention/name_call等）              |
| confidence         | Float              | NOT NULL                | 置信度（0-1）                                 |
| observed_at        | DateTime(timezone) | NOT NULL, DEFAULT now() | 观察时间                                     |

**索引：**

- 主键：`mention_id`
- 唯一约束：`(normalized_mention, person_id, scope_type, scope_id, evidence_type, source_message_id)`
- 索引：`idx_person_mentions_lookup` (normalized_mention, scope_type, scope_id, observed_at DESC)

---

### person_mention_frequencies

称呼频率统计表（LFU聚合）

| 字段名                         | 类型                 | 约束                      | 说明             |
| --------------------------- | ------------------ | ----------------------- | -------------- |
| person_mention_frequency_id | BigInteger         | PK, 自增                  | 频率ID           |
| normalized_mention          | Text               | NOT NULL                | 归一化称呼          |
| person_id                   | BigInteger         | NOT NULL                | 人物ID           |
| scope_type                  | Text               | NOT NULL                | 范围类型           |
| scope_id                    | Text               | NOT NULL, DEFAULT ''    | 范围ID           |
| lfu_state                   | JSONB              | NOT NULL, DEFAULT '{}'  | LFU状态（计数器/时间戳） |
| updated_at                  | DateTime(timezone) | NOT NULL, DEFAULT now() | 更新时间           |

**索引：**

- 主键：`person_mention_frequency_id`
- 唯一约束：`(normalized_mention, person_id, scope_type, scope_id)`
- 索引：`idx_person_mention_frequencies_lookup` (normalized_mention, scope_type, scope_id)

---

## 3. 会话与消息

### conversations

会话表

| 字段名              | 类型                 | 约束                      | 说明                  |
| ---------------- | ------------------ | ----------------------- | ------------------- |
| conversation_id  | BigInteger         | PK, 自增                  | 会话ID                |
| platform         | Text               | NOT NULL                | 平台名称                |
| account_id       | Text               | NOT NULL                | 账号ID                |
| platform_chat_id | Text               | NOT NULL                | 平台会话ID（群ID/私聊ID）    |
| chat_type        | Text               | NOT NULL                | 会话类型（group/private） |
| created_at       | DateTime(timezone) | NOT NULL, DEFAULT now() | 创建时间                |

**索引：**

- 主键：`conversation_id`
- 唯一约束：`(platform, account_id, platform_chat_id)`

---

### messages

消息表

| 字段名                  | 类型                 | 约束               | 说明                                           |
| -------------------- | ------------------ | ---------------- | -------------------------------------------- |
| message_id           | BigInteger         | PK, 自增           | 消息ID                                         |
| conversation_id      | BigInteger         | NOT NULL         | 会话ID（FK → conversations.conversation_id）     |
| ai_id                | Text               | NULLABLE         | AI实例ID（AI发的消息）                               |
| platform_identity_id | BigInteger         | NULLABLE         | 平台身份ID（FK → platform_identities.identity_id） |
| role                 | Text               | NOT NULL         | 角色（user/assistant/system/tool）               |
| content              | JSONB              | NOT NULL         | 消息内容（结构化：{text, images, tools等}）             |
| occurred_at          | DateTime(timezone) | NOT NULL         | 发生时间                                         |
| retain_until         | DateTime(timezone) | NULLABLE         | 保留截止时间（NULL=永久）                              |
| correlation_id       | Text               | NOT NULL         | 关联ID（跨系统追踪）                                  |
| source_key           | Text               | NULLABLE, UNIQUE | 来源唯一键（去重用）                                   |

**索引：**

- 主键：`message_id`
- 唯一约束：`source_key`

---

## 4. 记忆系统

### memories

记忆表（核心记忆存储）

| 字段名               | 类型                 | 约束                      | 说明                                  |
| ----------------- | ------------------ | ----------------------- | ----------------------------------- |
| memory_id         | BigInteger         | PK, 自增                  | 记忆ID                                |
| owner_ai_id       | Text               | NULLABLE                | 所属AI实例ID                            |
| person_id         | BigInteger         | NULLABLE                | 人物ID（FK → persons.person_id）        |
| session_id        | Text               | NULLABLE                | 会话ID                                |
| scope             | Text               | NOT NULL                | 作用域（self/person/group/global）       |
| memory_type       | Text               | NOT NULL                | 记忆类型（fact/preference/event等）        |
| content           | Text               | NOT NULL                | 记忆内容（Markdown格式）                    |
| embedding         | Vector             | NULLABLE                | 向量嵌入（用于语义检索）                        |
| importance        | Float              | NOT NULL                | 重要度（0-1）                            |
| strength          | Float              | NOT NULL                | 强度（衰减因子）                            |
| confidence        | Float              | NOT NULL                | 置信度（0-1）                            |
| emotion_intensity | Float              | NOT NULL, DEFAULT 0     | 情感强度（0-1）                           |
| protected         | Boolean            | NOT NULL, DEFAULT false | 是否受保护（不被清理）                         |
| dormant           | Boolean            | NOT NULL, DEFAULT false | 是否休眠（低优先级）                          |
| source            | JSONB              | NOT NULL, DEFAULT '{}'  | 来源（{type, message_id, confidence等}） |
| shared_with       | ARRAY(Text)        | NOT NULL, DEFAULT '{}'  | 共享给哪些AI                             |
| consolidated      | Boolean            | NOT NULL, DEFAULT false | 是否已整合（Episode合并后）                   |
| reference_count   | Integer            | NOT NULL, DEFAULT 0     | 被引用次数                               |
| created_at        | DateTime(timezone) | NOT NULL, DEFAULT now() | 创建时间                                |
| last_strength_at  | DateTime(timezone) | NOT NULL, DEFAULT now() | 最后强度更新时间                            |
| last_recalled_at  | DateTime(timezone) | NULLABLE                | 最后回忆时间                              |
| recall_count      | Integer            | NOT NULL, DEFAULT 0     | 回忆次数                                |
| lfu_state         | JSONB              | NOT NULL, DEFAULT '{}'  | LFU状态                               |

**索引：**

- 主键：`memory_id`

---

### memory_revisions

记忆修订表（记忆变更审计）

| 字段名                  | 类型                 | 约束                      | 说明                            |
| -------------------- | ------------------ | ----------------------- | ----------------------------- |
| revision_id          | BigInteger         | PK, 自增                  | 修订ID                          |
| memory_id            | BigInteger         | NOT NULL                | 记忆ID（FK → memories.memory_id） |
| supersedes_memory_id | BigInteger         | NULLABLE                | 被替代的记忆ID                      |
| changed_by           | Text               | NOT NULL                | 变更者（AI ID / system / manual）  |
| reason               | Text               | NOT NULL                | 变更原因                          |
| created_at           | DateTime(timezone) | NOT NULL, DEFAULT now() | 变更时间                          |

**索引：**

- 主键：`revision_id`

---

### conversation_episodes

会话片段表（一个Episode = 一段连续的对话）

| 字段名                | 类型                 | 约束                      | 说明                                       |
| ------------------ | ------------------ | ----------------------- | ---------------------------------------- |
| episode_id         | BigInteger         | PK, 自增                  | 片段ID                                     |
| activity_id        | Text               | NOT NULL, UNIQUE        | 活动ID（NATS消息ID）                           |
| ai_id              | Text               | NOT NULL                | AI实例ID                                   |
| person_id          | BigInteger         | NOT NULL                | 人物ID                                     |
| conversation_id    | BigInteger         | NOT NULL                | 会话ID（FK → conversations.conversation_id） |
| started_at         | DateTime(timezone) | NOT NULL                | 开始时间                                     |
| ended_at           | DateTime(timezone) | NOT NULL                | 结束时间                                     |
| summary            | Text               | NOT NULL, DEFAULT ''    | 片段摘要                                     |
| source_message_ids | ARRAY(BigInteger)  | NOT NULL, DEFAULT '{}'  | 来源消息ID列表                                 |
| estimated_tokens   | Integer            | NOT NULL, DEFAULT 0     | 预估Token数                                 |
| created_at         | DateTime(timezone) | NOT NULL, DEFAULT now() | 创建时间                                     |

**索引：**

- 主键：`episode_id`
- 唯一约束：`activity_id`
- 索引：`idx_conversation_episodes_owner` (ai_id, person_id, conversation_id, ended_at DESC)

---

### memory_atoms

原子记忆表（从Episode提取的原子事实）

| 字段名                | 类型                 | 约束                      | 说明                                                  |
| ------------------ | ------------------ | ----------------------- | --------------------------------------------------- |
| atom_id            | BigInteger         | PK, 自增                  | 原子ID                                                |
| ai_id              | Text               | NOT NULL                | AI实例ID                                              |
| owner_type         | Text               | NOT NULL                | 所有者类型（person/group/self）                            |
| owner_id           | Text               | NOT NULL                | 所有者ID                                               |
| person_id          | BigInteger         | NULLABLE                | 人物ID（如果是person类型）                                   |
| episode_id         | BigInteger         | NOT NULL                | 来源Episode ID（FK → conversation_episodes.episode_id） |
| memory_type        | Text               | NOT NULL                | 记忆类型                                                |
| content            | Text               | NOT NULL                | 内容                                                  |
| importance         | Float              | NOT NULL                | 重要度（0-1）                                            |
| confidence         | Float              | NOT NULL                | 置信度（0-1）                                            |
| source_message_ids | ARRAY(BigInteger)  | NOT NULL, DEFAULT '{}'  | 来源消息ID                                              |
| created_at         | DateTime(timezone) | NOT NULL, DEFAULT now() | 创建时间                                                |
| consolidated_at    | DateTime(timezone) | NULLABLE                | 整合时间（合并到Markdown）                                   |
| lfu_state          | JSONB              | NOT NULL, DEFAULT '{}'  | LFU状态                                               |

**索引：**

- 主键：`atom_id`
- 索引：`idx_memory_atoms_owner` (ai_id, owner_type, owner_id, created_at DESC)

---

### memory_documents

记忆文档表（Markdown格式的结构化记忆）

| 字段名                | 类型                 | 约束                      | 说明                       |
| ------------------ | ------------------ | ----------------------- | ------------------------ |
| memory_document_id | BigInteger         | PK, 自增                  | 文档ID                     |
| ai_id              | Text               | NOT NULL                | AI实例ID                   |
| owner_type         | Text               | NOT NULL                | 所有者类型（person/group/self） |
| owner_id           | Text               | NOT NULL                | 所有者ID                    |
| markdown_content   | Text               | NOT NULL                | Markdown内容               |
| version            | Integer            | NOT NULL, DEFAULT 1     | 版本号                      |
| lfu_state          | JSONB              | NOT NULL, DEFAULT '{}'  | LFU状态                    |
| updated_at         | DateTime(timezone) | NOT NULL, DEFAULT now() | 更新时间                     |

**索引：**

- 主键：`memory_document_id`
- 唯一约束：`(ai_id, owner_type, owner_id)`

---

### conversation_summaries

会话摘要表（长会话自动压缩）

| 字段名                     | 类型                 | 约束                      | 说明                                       |
| ----------------------- | ------------------ | ----------------------- | ---------------------------------------- |
| conversation_summary_id | BigInteger         | PK, 自增                  | 摘要ID                                     |
| ai_id                   | Text               | NOT NULL                | AI实例ID                                   |
| conversation_id         | BigInteger         | NOT NULL                | 会话ID（FK → conversations.conversation_id） |
| summary                 | Text               | NOT NULL                | 摘要内容                                     |
| version                 | Integer            | NOT NULL, DEFAULT 1     | 版本号                                      |
| updated_at              | DateTime(timezone) | NOT NULL, DEFAULT now() | 更新时间                                     |

**索引：**

- 主键：`conversation_summary_id`
- 唯一约束：`(ai_id, conversation_id)`

---

## 5. 直播管理

### live_sessions

直播会话表

| 字段名                | 类型                 | 约束               | 说明                   |
| ------------------ | ------------------ | ---------------- | -------------------- |
| live_session_id    | BigInteger         | PK, 自增           | 会话ID                 |
| session_id         | Text               | NOT NULL, UNIQUE | 会话UUID               |
| account_id         | Text               | NOT NULL         | 账号ID                 |
| director_policy_id | Text               | NOT NULL         | 导演策略ID               |
| status             | Text               | NOT NULL         | 状态（live/ended/error） |
| started_at         | DateTime(timezone) | NULLABLE         | 开始时间                 |
| ended_at           | DateTime(timezone) | NULLABLE         | 结束时间                 |

**索引：**

- 主键：`live_session_id`
- 唯一约束：`session_id`

---

### live_session_actors

直播角色表（AI在直播中的角色配置）

| 字段名                   | 类型         | 约束                      | 说明                                  |
| --------------------- | ---------- | ----------------------- | ----------------------------------- |
| live_session_actor_id | BigInteger | PK, 自增                  | 角色ID                                |
| session_id            | Text       | NOT NULL                | 会话ID（FK → live_sessions.session_id） |
| ai_id                 | Text       | NOT NULL                | AI实例ID                              |
| stage_slot            | Text       | NOT NULL                | 舞台位置（main/vocal/side等）              |
| is_lead               | Boolean    | NOT NULL, DEFAULT false | 是否主角                                |
| talk_weight           | Float      | NOT NULL, DEFAULT 1     | 发言权重                                |

**索引：**

- 主键：`live_session_actor_id`
- 唯一约束：`(session_id, ai_id)`

---

## 6. 扩展与工具

### extension_catalog

扩展目录表（工具注册中心）

| 字段名                  | 类型                 | 约束                      | 说明                                 |
| -------------------- | ------------------ | ----------------------- | ---------------------------------- |
| extension_catalog_id | BigInteger         | PK, 自增                  | 目录ID                               |
| tool_id              | Text               | NOT NULL, UNIQUE        | 工具唯一标识                             |
| provider_id          | Text               | NOT NULL                | 提供者ID                              |
| definition           | JSONB              | NOT NULL                | 工具定义（name/description/parameters等） |
| enabled              | Boolean            | NOT NULL, DEFAULT true  | 是否启用                               |
| updated_at           | DateTime(timezone) | NOT NULL, DEFAULT now() | 更新时间                               |

**索引：**

- 主键：`extension_catalog_id`
- 唯一约束：`tool_id`

---

### ai_extension_bindings

AI扩展绑定表（AI与工具的权限绑定）

| 字段名                     | 类型         | 约束                     | 说明                                   |
| ----------------------- | ---------- | ---------------------- | ------------------------------------ |
| ai_extension_binding_id | BigInteger | PK, 自增                 | 绑定ID                                 |
| ai_id                   | Text       | NOT NULL               | AI实例ID                               |
| tool_id                 | Text       | NOT NULL               | 工具ID（FK → extension_catalog.tool_id） |
| permission              | Text       | NOT NULL               | 权限级别（read/write/admin）               |
| config                  | JSONB      | NOT NULL, DEFAULT '{}' | 配置覆盖                                 |

**索引：**

- 主键：`ai_extension_binding_id`
- 唯一约束：`(ai_id, tool_id)`

---

### stickers

表情包表

| 字段名            | 类型                 | 约束                      | 说明          |
| -------------- | ------------------ | ----------------------- | ----------- |
| sticker_id     | BigInteger         | PK, 自增                  | 表情ID        |
| ai_id          | Text               | NOT NULL                | AI实例ID      |
| image_url      | Text               | NOT NULL                | 图片URL       |
| description    | Text               | NOT NULL                | 描述          |
| tags           | ARRAY(Text)        | NOT NULL                | 标签列表        |
| match_quality  | Float              | NOT NULL                | 匹配质量（LLM评分） |
| usage_strength | Float              | NOT NULL                | 使用强度（LFU）   |
| boost_count    | Integer            | NOT NULL                | 人为提升次数      |
| created_at     | DateTime(timezone) | NOT NULL, DEFAULT now() | 创建时间        |
| last_used_at   | DateTime(timezone) | NULLABLE                | 最后使用时间      |

**索引：**

- 主键：`sticker_id`

---

### qzone_commented_feeds

QQ空间已评论动态表（去重记录）

| 字段名                     | 类型                 | 约束                      | 说明   |
| ----------------------- | ------------------ | ----------------------- | ---- |
| qzone_commented_feed_id | BigInteger         | PK, 自增                  | 记录ID |
| account_id              | Text               | NOT NULL                | 账号ID |
| feed_id                 | Text               | NOT NULL                | 动态ID |
| commented_at            | DateTime(timezone) | NOT NULL, DEFAULT now() | 评论时间 |

**索引：**

- 主键：`qzone_commented_feed_id`
- 唯一约束：`(account_id, feed_id)`

---

## 7. 运营与审计

### audit_log

审计日志表

| 字段名         | 类型                 | 约束                      | 说明                          |
| ----------- | ------------------ | ----------------------- | --------------------------- |
| audit_id    | BigInteger         | PK, 自增                  | 日志ID                        |
| actor_type  | Text               | NOT NULL                | 操作者类型（ai/user/system）       |
| actor_id    | Text               | NOT NULL                | 操作者ID                       |
| action      | Text               | NOT NULL                | 操作类型（create/update/delete等） |
| target_type | Text               | NOT NULL                | 目标类型                        |
| target_id   | Text               | NOT NULL                | 目标ID                        |
| reason      | Text               | NOT NULL, DEFAULT ''    | 操作原因                        |
| result      | JSONB              | NOT NULL, DEFAULT '{}'  | 结果详情                        |
| created_at  | DateTime(timezone) | NOT NULL, DEFAULT now() | 操作时间                        |

**索引：**

- 主键：`audit_id`

---

### panel_settings

运维面板设置表

| 字段名              | 类型         | 约束               | 说明   |
| ---------------- | ---------- | ---------------- | ---- |
| panel_setting_id | BigInteger | PK, 自增           | 设置ID |
| key              | Text       | NOT NULL, UNIQUE | 设置键  |
| value            | Text       | NOT NULL         | 设置值  |

**索引：**

- 主键：`panel_setting_id`
- 唯一约束：`key`

---

## 附录

### 枚举类型说明

#### scope（记忆作用域）

- `self`：AI自身的记忆
- `person`：关于某个人的记忆
- `group`：关于某个群的记忆
- `global`：全局记忆

#### memory_type（记忆类型）

- `fact`：事实性记忆
- `preference`：偏好记忆
- `event`：事件记忆
- `relationship`：关系记忆
- `instruction`：指令记忆

#### chat_type（会话类型）

- `group`：群聊
- `private`：私聊

#### role（消息角色）

- `user`：用户消息
- `assistant`：AI回复
- `system`：系统提示
- `tool`：工具调用结果

#### ceiling_policy（上限策略）

- `restricted`：受限（低互动）
- `normal`：正常
- `intimate`：亲密（高互动）

### 通用字段说明

#### lfu_state (JSONB)

Least Frequently Used 状态，用于记忆衰减算法：

```json
{
  "access_count": 123,
  "last_access_at": "2026-08-26T10:00:00Z",
  "half_life_days": 30,
  "current_strength": 0.85
}
```

#### source (JSONB)

记忆来源元数据：

```json
{
  "type": "message|episode|manual",
  "message_id": 12345,
  "confidence": 0.95,
  "extracted_by": "ai-agent-v1"
}
```

#### content (JSONB)

消息内容结构：

```json
{
  "text": "消息文本",
  "images": ["url1", "url2"],
  "tools": [{"name": "tool1", "result": {...}}],
  "reply_to": "message_id"
}
```

---

*最后更新：2026-08-26*
*文档维护：ai-love 项目组*
