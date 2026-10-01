# 插件实例、操作与数据所有权

本文定义目标数据契约。artifact sha256 对应内容完整性，generation 对应单写者代次，revision 对应条件更新。

## 实体结果

| 实体 | 字段 | 归属 |
| --- | --- | --- |
| PluginArtifact | plugin_id、artifact_path、sha256、entrypoint、manifest | 批准的本地产物目录与控制记录 |
| PluginManifest | provides、requires、instance_scope、config_schema、permissions_requested、isolation、upgrade_mode、state、limits、ui | contracts/plugin.schema.json |
| PluginInstance | instance_id、plugin_id、host_id、scope、artifact_digest、desired_enabled、actual_state、generation、config_revision、grant_revision、last_error | PostgreSQL plugin_instances |
| CapabilityBinding | binding_id、host_id、capability、scope_key、provider_instance_id、position、revision、activation_state | PostgreSQL plugin_bindings |
| PluginOperation | operation_id、actor_id、action、scope、expected_revision、request_hash、phase、candidate_instance_id、previous_instance_id、deadline_at、error、created_at、updated_at | PostgreSQL plugin_operations |
| ConfigSnapshot | instance_id、revision、content、content_hash、created_at | 受限控制快照 |
| PermissionGrant | grant_id、instance_id、operations、ai/account scope、resource_allowlist、limits、revision、revoked_at | 可信管理授权 |
| ResourceLease | resource_id、instance_id、kind、borrowed、state、deadline、generation | 实例 ResourceScope |
| StateHandoff | operation_id、owner_scope、snapshot_uri、checksum、db_watermark、kv_watermarks、pending_work_keys、stage、recovery_instructions | 受限目录与控制元数据 |

Artifact 对应多个 Instance，Instance 对应 Binding、Lease、ConfigSnapshot 及 Grant，Operation 关联候选、原实例及 Handoff。单提供者 capability/scope 具有唯一活动绑定，有序策略 position 唯一。

## Scope 与状态

Scope 结构为 `{kind, ai_id?, account_id?, session_id?, device_id?}`，合法字段由 kind 确定。调用具有 invocation_id、event_id/run_id、deadline、受众、授权及幂等键，身份由可信入口确定。

| 实际状态 | 结果含义 |
| --- | --- |
| DISCOVERED | 已核验目录项 |
| LOADED | 已取得工厂与执行句柄 |
| INITIALIZED | 配置及候选能力就绪 |
| RUNNING | 当前活动绑定具有执行资格 |
| STOPPED | 已接收工作具有排空结果 |
| DISPOSED | 实例资源已释放 |
| UNLOADED | 执行句柄已回收 |
| FAILED | 阶段、资源及恢复状态可定位 |

desired_enabled 记录管理意图。操作状态为 requested、prepared、quiesced、committed、cleaned/completed，恢复结果采用 failed/compensating/needs_recovery 等准确记录。活动绑定、代次和 committed 具有同一事务凭证。

## 业务所有权

| 数据 | 权威范围 | 保留结果 |
| --- | --- | --- |
| 人物、身份、账号、会话、消息 | Identity / Conversation 端口 | 稳定 ID、来源、账号、引用与受众 |
| 私聊任务、额度、发送账本 | 核心动作协调与平台持久层 | 锁顺序、claim_version、run_id、摘要和 unknown |
| Episode、Atom、文档及 KV | Memory owner | 来源、水位、CAS、person/self 和 pending 集合 |
| 人物关系 | ai_id + person_id | 多维关系及白名单规则 |
| 表情素材 | AI 资源范围 | 文件、评分与使用资料 |
| Redis 会话及群记录 | SessionPort | AI 范围与 TTL 语义 |

持久结构沿用既有物理表和 Alembic 历史，控制表采用追加迁移，插件私有结构具有独立登记范围。状态交接成功依据所有权、checksum、水位、工作集合与旧写入者静止证据。插件移除保留用户数据、迁移记录和恢复资料。
