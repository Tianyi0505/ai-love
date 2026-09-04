# 数据库重构方案

> 创建时间：2026-08-26
> 最后更新：2026-08-26
> 目标：简化表结构、删除冗余字段、统一主键策略、优化记忆系统、删除运营审计与扩展管理表

---

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-08-26 | 初始版本：ai_id 主键化、social_accounts 精简、记忆系统重构 |
| v2.0 | 2026-08-26 | 新增：直播/扩展表删除（改为配置化）、QQ 空间 Redis 方案、工具权限 Nacos 配置 |
| v2.1 | 2026-08-26 | 新增：删除 audit_log 和 panel_settings（运营审计需求已移除，配置迁移到 Nacos） |
| v2.2 | 2026-08-26 | 重构：ai_id 自增主键化（部分表允许）、删除 4.2/4.3 无效章节、QQ 空间改为 per-friend Redis 游标、ai_profiles 确认删除、owner_id 拆分为 owner_ai_id/owner_person_id |

---

## 一、当前问题分析

### 1.1 ai_id 设计问题

**现状**：`ai_id` 是 Text 类型，在多个表中作为外键关联

**问题**：
- 无法利用数据库级联删除/更新
- 关联查询性能差（字符串 JOIN vs 数值 JOIN）
- 占用空间大（Text vs BigInteger）

**决策**：
- **核心表**（ai_account_bindings, person_relationships, group_relationships, person_memories, conversation_summaries）：ai_id 改为 BigInteger 自增主键，走 `ai_ids` 表
- **允许例外**：部分表（如 stickers）可继续使用文本 ID，不强求统一

### 1.2 冗余字段

- `ai_profiles.profile_id`：与 `ai_id` 重复，删除
- `social_accounts.credential_ref`：Nacos 配置无需持久化到 DB
- `social_accounts.status`：状态由服务层维护，DB 仅作缓存无意义
- `social_accounts.is_live_platform`：硬编码字段，应由平台配置决定
- `social_accounts.allows_multi_ai`：业务规则不应硬编码在表结构

### 1.3 记忆系统过度设计

当前有 6 张记忆相关表，逻辑重叠严重：
- `memories`（主记忆表）vs `memory_atoms`（原子记忆）vs `memory_documents`（Markdown文档）
- `conversation_episodes`（会话片段）vs `conversation_summaries`（会话摘要）

**问题**：
- 同一事实在多表重复存储
- `memory_atoms` 和 `memory_documents` 功能重叠
- `memories` 表实际为死代码（仅有 postgres_memory_repository.py 读取，无写入路径）

**方案**：简化为 2 张表
- `person_memories`：按人维度的记忆（人物关系、偏好、事实），owner_ai_id 区分不同 AI 的记忆，支持跨 AI 共享
- `conversation_summaries`：会话摘要压缩表
- `messages` 保持不变（用于原始消息检索）

### 1.4 直播与扩展系统过度设计

**问题**：
- `live_session_actors`：仅存储 AI 角色配置，业务逻辑简单无需 DB 持久化
- `extension_catalog` + `ai_extension_bindings`：工具权限应通过配置文件管理，而非 DB
- 工具调用权限不应与 AI 实例硬绑定

**方案**：
- 删除 `live_session_actors`，直播角色配置改为内存对象
- 删除 `extension_catalog` + `ai_extension_bindings`，工具注册与权限走 Nacos 配置
- 所有 AI 共享工具池，通过配置文件控制可用工具

---

## 二、表删除清单

### 2.1 完全删除的表

| 表名 | 删除原因 | 数据迁移方案 |
|------|---------|-------------|
| `ai_profiles` | Nacos 为唯一数据源，DB 副本冗余 | 删除，启动逻辑改用 `nacos_agent_definition_store.list_active()` |
| `memories` | 死代码表（仅 postgres_memory_repository 读取，无写入路径） | 清空删除，不迁移 |
| `memory_atoms` | 功能重叠，合并到 `person_memories` | 数据迁移到 `person_memories.content` |
| `memory_documents` | 功能重叠，合并到 `person_memories` | 数据迁移到 `person_memories.content` |
| `memory_revisions` | 审计需求已移除，直接删除 | 清空删除 |
| `person_mentions` | 称呼解析应在服务层缓存，无需持久化 | 清空删除 |
| `person_mention_frequencies` | 同上 | 清空删除 |
| `audit_log` | 运营审计需求已移除 | 清空删除 |
| `panel_settings` | 运维面板配置迁移到 Nacos `ailove.panel.settings` | 迁移到 Nacos，删除表 |
| `qzone_commented_feeds` | 改用 Redis 记录 per-friend 游标 | 迁移到 Redis（见第十章） |
| `live_session_actors` | 改为内存对象 + Nacos 配置 | 数据迁移到配置文件 |
| `extension_catalog` | 迁移到 Nacos `ailove.tools.registry` | 迁移到配置中心 |
| `ai_extension_bindings` | 迁移到 Nacos `ailove.tools.permissions` | 迁移到配置中心 |

**保留表**：
- `stickers`（表情包）：AI 个性化数据，保留 DB 存储

---

## 三、表结构修改方案

### 3.1 新增 `ai_ids` 表

**目的**：统一 AI 实例主键，替代所有外键中的 Text 类型 `ai_id`

**设计决策**：
- **纯 Slug 注册表**：仅存储 `ai_slug`（外部引用标识）+ `ai_id`（自增主键）
- **移除冗余字段**：`display_name` / `status` 等元数据由 Nacos 配置管理，不在 DB 存储

```sql
CREATE TABLE ai_ids (
    ai_id      BigInteger GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ai_slug    Text NOT NULL UNIQUE,              -- 外部引用用 slug（如 ai_luoyu）
    created_at DateTime(timezone=True) NOT NULL DEFAULT now(),
    updated_at DateTime(timezone=True) NOT NULL DEFAULT now()
);
```

**影响范围**：以下表的外键 `ai_id` (Text) → `ai_id` (BigInteger, FK → ai_ids.ai_id)

| 表名 | 修改内容 |
|------|---------|
| `ai_account_bindings` | `ai_id` BigInteger NOT NULL → FK `ai_ids.ai_id` |
| `person_relationships` | `ai_id` Text NOT NULL → FK `ai_ids.ai_id` |
| `group_relationships` | `ai_id` Text NOT NULL → FK `ai_ids.ai_id` |
| `person_memories` | `ai_id` Text NOT NULL → FK `ai_ids.ai_id` |
| `conversation_summaries` | `ai_id` Text NOT NULL → FK `ai_ids.ai_id` |
| `stickers` | **新增** `ai_id` BigInteger FK（nullable，NULL=全局表情包，非 NULL=AI 专属） |

**迁移策略**：
1. 创建 `ai_ids` 表
2. 从 `nacos_agent_definition_store.list_active()` 批量迁移 `ai_slug`
3. 更新所有外键引用
4. 删除 `ai_profiles` 表

**启动时 Slug 解析**：
- 服务启动时从 `ai_ids` 全量加载 `ai_slug` → `ai_id` 映射到内存缓存
- Nacos 配置中的 `ai_id: ai_luoyu` 解析为 `ai_id: 1`（示例）

---

### 3.2 `social_accounts` 精简

**删除字段**：
- `credential_ref`
- `status`
- `is_live_platform`
- `allows_multi_ai`

**保留字段**：
- `social_account_id` (PK)
- `account_id` (UNIQUE)
- `platform`
- `platform_account_id`
- `display_name`
- `created_at`

**唯一约束保留**：`(platform, platform_account_id)`

---

### 3.3 工具权限控制方案（配置化）

**原则**：工具注册与权限由 Nacos 配置中心统一管理，DB 不存储工具元数据

#### 3.3.1 工具注册（Nacos 配置）

**配置 Key**：`ailove.tools.registry`

**配置示例**：
```yaml
tools:
  - tool_id: "web_search"
    provider_id: "tavily"
    enabled: true
    config:
      api_key_env: "TAVILY_API_KEY"
      max_results: 10

  - tool_id: "image_generation"
    provider_id: "openai"
    enabled: true
    config:
      model: "dall-e-3"
      api_key_env: "OPENAI_API_KEY"

  - tool_id: "code_interpreter"
    provider_id: "local"
    enabled: true
    config:
      timeout: 60
      sandbox: true
```

#### 3.3.2 AI 权限配置（Nacos 配置）

**配置 Key**：`ailove.tools.permissions`

**配置示例**：
```yaml
ai_permissions:
  - ai_uuid: "ai_luoyu"
    allowed_tools:
      - "web_search"
      - "image_generation"
    denied_tools:
      - "code_interpreter"

  - ai_uuid: "ai_huang"
    allowed_tools: ["*"]  # 全部工具
    denied_tools: []
```

**说明**：
- 所有 AI 共享工具池，通过配置文件控制可用工具
- 启动时从 Nacos 拉取配置，内存缓存（5 分钟 TTL）
- 不支持 DB 级联，改为配置热更新（监听 Nacos 变更）

---

### 3.4 记忆系统重构

**核心设计决策**：
- `owner_ai_id`：区分**哪个 AI 的记忆**，支持跨 AI 记忆共享（跨 AI 共享场景下，AI A 可读取 AI B 对某人的记忆）
- `person_id`：记忆的主体（被描述的人）

#### 3.4.1 新增 `person_memories`

**用途**：按人维度的结构化记忆（关系、偏好、事实）

```sql
CREATE TABLE person_memories (
    memory_id         BigInteger GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_ai_id       BigInteger NOT NULL REFERENCES ai_ids(ai_id),  -- 哪个 AI 的记忆
    person_id         BigInteger NOT NULL REFERENCES persons(person_id),  -- 关于谁
    memory_type       Text NOT NULL,                    -- fact/preference/event/relationship
    content           Text NOT NULL,                    -- Markdown 格式
    importance        Float NOT NULL DEFAULT 0.5,       -- 0-1
    confidence        Float NOT NULL DEFAULT 0.8,       -- 0-1
    source            JSONB NOT NULL DEFAULT '{}',      -- 来源元数据
    lfu_state         JSONB NOT NULL DEFAULT '{}',      -- LFU 衰减
    created_at        DateTime(timezone=True) NOT NULL DEFAULT now(),
    updated_at        DateTime(timezone=True) NOT NULL DEFAULT now(),
    last_recalled_at  DateTime(timezone=True),          -- 最后回忆时间
    recall_count      Integer NOT NULL DEFAULT 0,
    UNIQUE(owner_ai_id, person_id, memory_type, content)  -- 去重
);
```

**索引**：
```sql
CREATE INDEX idx_person_memories_lookup ON person_memories(owner_ai_id, person_id, importance DESC);
CREATE INDEX idx_person_memories_type ON person_memories(owner_ai_id, memory_type);
```

---

#### 3.4.2 修改 `conversation_summaries`

**修改内容**：
- `ai_id` → FK `ai_ids.ai_id`（BigInteger）
- 删除 `version` 字段（冗余）
- `(ai_id, conversation_id)` 联合主键

**新结构**：
```sql
CREATE TABLE conversation_summaries (
    ai_id              BigInteger NOT NULL REFERENCES ai_ids(ai_id),
    conversation_id    BigInteger NOT NULL REFERENCES conversations(conversation_id),
    summary            Text NOT NULL,                -- 压缩摘要
    message_count      Integer NOT NULL DEFAULT 0,   -- 压缩的消息数
    started_at         DateTime(timezone=True) NOT NULL,
    ended_at           DateTime(timezone=True) NOT NULL,
    created_at         DateTime(timezone=True) NOT NULL DEFAULT now(),
    updated_at         DateTime(timezone=True) NOT NULL DEFAULT now(),
    PRIMARY KEY (ai_id, conversation_id)
);
```

**索引**：
```sql
CREATE INDEX idx_conv_summaries_time ON conversation_summaries(ai_id, ended_at DESC);
```

**注**：embedding 检索和 BM25 功能暂不实现（embedding 字段 + BM25 索引推迟到引入 Elasticsearch 时再添加）

---

#### 3.4.3 保留 `messages` 但精简

**删除字段**：
- `ai_id` → 改为 `created_by_ai_id` BigInteger（FK → ai_ids.ai_id），仅 AI 主动发消息时填充
- `embedding`（如果存在）→ 完全删除，消息表不存 embedding
- `retain_until` → 改为 `expires_at`，NULL = 永久保留
- **保留 `source_key`**：JetStream 幂等性关键字段，禁止删除

**保留字段**：
- `message_id` (PK)
- `conversation_id` (FK)
- `platform_identity_id` (FK)
- `role`
- `content` (JSONB)
- `occurred_at`
- `correlation_id`
- `source_key` (Text, Unique) - **保留，用于消息去重**

**新增字段**：
- `created_by_ai_id` BigInteger FK（nullable，仅 AI 主动消息）

---

#### 3.4.4 删除 `memories` 表

**原因**：死代码表，仅有 postgres_memory_repository.py 读取（已废弃），无写入路径

**数据迁移**：无（数据已无实际写入，直接删除）

---

### 3.5 `conversation_episodes` 简化

**保留用途**：会话片段元数据（用于触发摘要压缩）

**精简字段**：
- 删除 `estimated_tokens`（Episode 不再追踪 token 统计）
- 删除 `activity_id` → 改为自增主键 `episode_id`
- **保留 `ai_id`**（改为 FK `ai_ids.ai_id`）
- **保留 `person_id`**
- **保留 `activity_id` 唯一约束的语义**：通过 `(ai_id, person_id, conversation_id, started_at)` 联合唯一索引实现幂等

**新结构**：
```sql
CREATE TABLE conversation_episodes (
    episode_id         BigInteger GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ai_id              BigInteger NOT NULL REFERENCES ai_ids(ai_id),
    person_id          BigInteger NOT NULL REFERENCES persons(person_id),
    conversation_id    BigInteger NOT NULL REFERENCES conversations(conversation_id),
    started_at         DateTime(timezone=True) NOT NULL,
    ended_at           DateTime(timezone=True) NOT NULL,
    summary            Text NOT NULL DEFAULT '',
    source_message_ids ARRAY(BigInteger) NOT NULL DEFAULT '{}',
    created_at         DateTime(timezone=True) NOT NULL DEFAULT now(),
    UNIQUE(ai_id, person_id, conversation_id, started_at)  -- 幂等键
);
```

---

### 3.6 其他表微调

#### `group_relationships`
- `ai_id` → FK `ai_ids.ai_id`

#### `person_relationships`
- `ai_id` → FK `ai_ids.ai_id`

#### `ai_account_bindings`
- `ai_id` → FK `ai_ids.ai_id`

---

## 四、迁移步骤

### 4.1 前置条件

#### Redis AOF 持久化配置

**要求**：QQ 空间游标数据必须持久化，防止重启丢失

**配置修改**：
- Redis 启动参数：`--appendonly yes`（从 `--appendonly no` 改为开启）
- 数据卷挂载：`/opt/ailove/k8s-data/redis`（与 NATS 卷模式一致）

**修改文件**：
- `deploy/k8s/infrastructure.yaml`（line 36）
- `deploy/docker-compose.yml`
- `deploy/docker-compose.cloud.yml`

---

#### Migration 0006 前置：0003-0005 防御性加固

**问题**：现有迁移 0003/0005 硬引用了即将删除的表（`memories`, `memory_atoms`, `memory_documents`），新环境初始化会失败

**要求**：在执行 0006 前，必须先为 0003-0005 添加防御性检查

**加固模式**：
```python
def upgrade():
    # 防御性检查：表存在才操作
    conn = op.get_bind()
    if _has_table(conn, 'memory_atoms'):
        # 原有逻辑
        ...
```

**验证**：新环境干净初始化（`stamp 0001_initial + upgrade head`）必须成功

---

### 4.2 Alembic 迁移脚本规划

**迁移 0006：ai_id 主键化 + ai_ids 表**
1. 创建 `ai_ids` 表
2. 从 Nacos 配置（`agent.catalog.active_ai_ids`）批量迁移 `ai_slug`
3. `stickers` 表新增 `ai_id` BigInteger FK（nullable）
4. 所有外键 `ai_id` Text → BigInteger + FK 约束（见 3.1 影响范围表）
5. 删除 `ai_profiles` 表

**迁移 0007：social_accounts 精简 + 删除运营/直播/扩展表**
1. `social_accounts` 删除冗余字段
2. 删除 `audit_log`（运营审计需求已移除）
3. 删除 `panel_settings`（配置迁移到 Nacos `ailove.panel.settings`）
4. 删除 `live_session_actors`（数据迁移到配置文件）
5. 删除 `extension_catalog`（迁移到 Nacos）
6. 删除 `ai_extension_bindings`（迁移到 Nacos）
7. 重建唯一约束

**迁移 0008：记忆系统重构**
1. 创建 `person_memories`
2. 创建新版 `conversation_summaries`（删除 version 字段）
3. `messages` 删除 `embedding`/`retain_until`，新增 `created_by_ai_id`
4. `conversation_episodes` 删除 `estimated_tokens`/`activity_id`，新增 `episode_id`
5. 删除 `memories`（死代码，直接删除）
6. 删除 `memory_atoms`/`memory_documents`/`memory_revisions`（数据迁移到 person_memories）

**迁移 0009：QQ空间去重迁移 + 索引优化**
1. `qzone_commented_feeds` 数据迁移到 Redis（见第十章）
2. 删除 `qzone_commented_feeds` 表
3. 创建 `person_memories` 和 `conversation_summaries` 所需索引

---

### 4.3 回滚方案

每个迁移脚本必须包含 `downgrade()` 实现，回滚顺序与升级相反。

---

### 4.4 停机窗口

- **预计时间**：30-60 分钟（数据量大时）
- **建议时间**：凌晨低峰期
- **影响范围**：全服务（共享数据库）

---

## 五、QQ 空间 Redis 方案

### 5.1 设计目标

**问题**：原表 `qzone_commented_feeds` 仅记录是否评论过某动态，无法支持"跳过好友更早动态"的语义

**新方案**：per-friend 游标（记录每个好友最后浏览到的说说时间戳）

**核心设计**：
- 每个好友（friend_uin）独立维护游标
- 下一次扫描时，跳过该好友所有 `timestamp <= cursor` 的说说
- 避免遗漏不同好友之间时间交错的新动态

### 5.2 Redis Key 设计

#### 5.2.1 好友游标 Key

**Key 格式**：`qzone:cursor:{account_id}:{friend_uin}`

**Value**（String，Unix 时间戳）：
```json
"1699234567"
```

**语义**：该账号下该好友最后浏览到的说说发布时间戳

#### 5.2.2 已评论动态 Key

**Key 格式**：`qzone:commented:{account_id}:{friend_uin}`

**Value**（Set）：
```
"fef3wfewfwe"  # feed.tid
"abc123xyz"
```

**语义**：该账号下该好友所有已评论的动态 ID（支持"被回复才接着回"的语义）

#### 5.2.3 过期策略

- **cursor Key**：永不过期（好友关系持续存在）
- **commented Key**：7 天过期（超过 7 天的动态不再追踪回复）

### 5.3 操作流程

```python
import redis
import time

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def update_friend_cursor(account_id: str, friend_uin: str, latest_timestamp: int):
    """更新好友游标（浏览完该好友所有说说后调用）"""
    key = f"qzone:cursor:{account_id}:{friend_uin}"
    redis_client.set(key, latest_timestamp)

def get_friend_cursor(account_id: str, friend_uin: str) -> int:
    """获取好友游标（扫描前调用）"""
    key = f"qzone:cursor:{account_id}:{friend_uin}"
    timestamp = redis_client.get(key)
    return int(timestamp) if timestamp else 0

def mark_feed_commented(account_id: str, friend_uin: str, feed_tid: str):
    """标记动态已评论"""
    key = f"qzone:commented:{account_id}:{friend_uin}"
    redis_client.sadd(key, feed_tid)
    redis_client.expire(key, 7 * 86400)  # 7天过期

def is_feed_commented(account_id: str, friend_uin: str, feed_tid: str) -> bool:
    """检查动态是否已评论"""
    key = f"qzone:commented:{account_id}:{friend_uin}"
    return redis_client.sismember(key, feed_tid)

def get_replied_feeds(account_id: str, friend_uin: str) -> set[str]:
    """获取该好友所有被回复过的动态 ID（触发追评逻辑）"""
    key = f"qzone:commented:{account_id}:{friend_uin}"
    return redis_client.smembers(key)
```

### 5.4 扫描流程

```python
async def scan_friend_feeds(account_id: str, friend_uin: str):
    """扫描好友说说（跳过已浏览）"""
    cursor = get_friend_cursor(account_id, friend_uin)

    # 拉取说说（假设每次最多 20 条）
    feeds = await qzone_api.list_feeds_by_uin(friend_uin, num=20)

    # 过滤：跳过 cursor 之前的说说
    new_feeds = [f for f in feeds if f.timestamp > cursor]

    # 去重：跳过已评论（除非被回复）
    for feed in new_feeds:
        if is_feed_commented(account_id, friend_uin, feed.tid):
            # 检查是否被回复，若被回复则追评
            if await has_reply_to_our_comment(account_id, feed.tid):
                await generate_reply_comment(account_id, feed)
            continue

        # 处理新说说（评论/点赞）
        await process_feed(account_id, feed)
        mark_feed_commented(account_id, friend_uin, feed.tid)

    # 更新游标（该好友最新一条说说的 timestamp）
    if new_feeds:
        latest_ts = max(f.timestamp for f in new_feeds)
        update_friend_cursor(account_id, friend_uin, latest_ts)
```

### 5.5 优势

- **精确游标**：per-friend 设计避免时间交错导致的遗漏
- **轻量**：String + Set，无表结构开销
- **高性能**：读写延迟 < 1ms
- **持久化**：Redis AOF 保证重启不丢游标
- **易扩展**：可轻松添加 `daily_like_count`、`daily_comment_count` 等字段

---

## 六、性能预期

### 6.1 存储空间优化

| 优化项 | 预计节省 |
|--------|---------|
| ai_id 统一主键（核心表） | 约 20%（字符串 → 数值，仅影响 6 张核心表） |
| 删除冗余字段 | 约 10% |
| 删除 12 张冗余/死代码表 | 约 15% |

**总计**：存储空间减少约 30-40%

**注**：移除了原方案中不准确的"messages 移除 embedding 节省 40%"（messages 实际无 embedding 字段）、"JOIN 性能提升 2-3x"（基础基数小，收益有限）

---

### 6.2 查询性能

| 查询场景 | 延迟 | 备注 |
|---------|------|------|
| person_memories 查询 | < 5ms | 缓存命中率 95%+ |
| conversation_summaries 查询 | < 10ms | 按时间范围查询 |
| 新增/更新 AI 配置 | < 10ms | ai_ids 表基数小（<100 行） |

**注**：移除了原方案中未实现的 embedding 向量检索和 BM25 检索性能指标

---

## 七、风险评估

### 7.1 高风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| ai_id 外键断裂 | 全服务不可用 | 迁移脚本必须包含数据校验步骤，失败自动回滚 |
| Redis 游标丢失 | QQ 空间重复评论 | AOF 持久化必须开启，定期备份 Redis RDB |

### 7.2 中风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 迁移顺序错误 | 新环境初始化失败 | 严格执行 0006 前置条件（0003-0005 加固验证） |
| Nacos 配置与 DB 不一致 | AI 实例启动失败 | 迁移后执行一致性校验脚本 |

---

## 八、后续优化

### 8.1 短期（Q3 2026）

- [ ] 完成迁移脚本（0006-0009）
- [ ] 实现记忆召回服务（person_memories + conversation_summaries 查询优化）
- [ ] 实现 QQ 空间 per-friend 游标逻辑

### 8.2 中期（Q4 2026）

- [ ] 引入 Elasticsearch + embedding 向量检索
- [ ] 实现 BM25 全文检索
- [ ] 实现记忆重要性自动评分（LLM 评估）
- [ ] 实现 LFU 衰减自动任务（每日凌晨）

### 8.3 长期（2027）

- [ ] 跨 AI 记忆共享（owner_ai_id 字段支持）
- [ ] 多模态记忆支持（图片/音频摘要）
- [ ] 记忆遗忘策略自动执行（删除低强度记忆）

---

## 九、附录：新旧表映射

| 旧表 | 新表/替代方案 | 映射关系 |
|------|-------------|---------|
| `ai_profiles` | `ai_ids` | 删除，改用 Nacos `list_active()` |
| `memories` | 直接删除 | 死代码表，无数据迁移 |
| `memory_atoms` | `person_memories` | 合并到 content |
| `memory_documents` | `person_memories` | 合并到 content |
| `memory_revisions` | 直接删除 | 清空删除 |
| `person_mentions` | 直接删除 | 清空删除 |
| `person_mention_frequencies` | 直接删除 | 清空删除 |
| `audit_log` | 直接删除 | 运营审计需求已移除 |
| `panel_settings` | Nacos `ailove.panel.settings` | 运维面板配置迁移到配置中心 |
| `messages` | `messages` | 删除 embedding/retain_until，保留 source_key，新增 created_by_ai_id |
| `conversation_episodes` | `conversation_episodes` | 删除 estimated_tokens/activity_id，新增 episode_id |
| `conversation_summaries` | `conversation_summaries` | 删除 version，ai_id 改为 FK |
| `person_memories` | `person_memories` | 新增表（替代 memories + memory_atoms + memory_documents） |
| `stickers` | `stickers` | **保留**，新增 ai_id FK（nullable） |
| `qzone_commented_feeds` | Redis（per-friend cursor） | `qzone:cursor:{account_id}:{friend_uin}` + `qzone:commented:{account_id}:{friend_uin}` |
| `live_session_actors` | 内存对象 + Nacos 配置 | 删除，改为配置驱动 |
| `extension_catalog` | Nacos `ailove.tools.registry` | 迁移到配置中心 |
| `ai_extension_bindings` | Nacos `ailove.tools.permissions` | 迁移到配置中心 |

---

## 十、附录：运维面板配置方案

### 10.1 配置 Key

**Key**：`ailove.panel.settings`

### 10.2 配置示例

```yaml
panel:
  # 基础配置
  default_username: "ai-love"
  default_password: "ai-love"

  # 界面配置
  theme: "light"  # light/dark
  language: "zh-CN"

  # 功能开关
  features:
    agent_runs_replay: true
    memory_browser: true
    system_health: true
    log_viewer: false

  # 导航链接
  nav_links:
    - name: "Nacos"
      url: "http://nacos.ailove.local:8848/nacos"
    - name: "K3s Dashboard"
      url: "http://k3s-dashboard.ailove.local:30443"
```

### 10.3 迁移脚本

```python
# 迁移 0007 子步骤：panel_settings → Nacos
def upgrade():
    # 读取现有配置
    conn = op.get_bind()
    result = conn.execute(text("SELECT key, value FROM panel_settings"))
    settings = {row[0]: row[1] for row in result}

    # 写入 Nacos 配置
    nacos_client = NacosClient()
    nacos_client.publish_config(
        data_id="ailove.panel.settings",
        content=yaml.dump(settings, allow_unicode=True),
        group="DEFAULT_GROUP"
    )

    # 删除表
    op.drop_table('panel_settings')
```

---

*文档版本：v2.2*
*最后更新：2026-08-26*
*审核状态：待评审*
*下一步：评审后生成 Alembic 迁移脚本*
