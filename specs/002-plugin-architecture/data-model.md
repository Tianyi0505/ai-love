# Data Model: 插件实例、操作和数据所有权

仅描述当前契约；无插件/API/配置/状态格式版本字段。数据的 schema、数据库迁移历史、配置修订与租约代次不用于插件版本管理。

## 实体与关联

| 实体 | 字段与约束 | 持久位置 / 关联 |
|---|---|---|
| PluginArtifact | plugin_id、artifact_path、sha256、entrypoint、manifest；只接受批准目录/摘要，不执行发现期 import | 本地安装目录；数据库保留当前/候选产物记录，无历史版本选择接口 |
| PluginManifest | provides、requires、instance_scope、config_schema、permissions_requested、isolation、upgrade_mode、state、limits、ui | contracts/plugin.schema.json；不得出现版本协商字段 |
| PluginInstance | instance_id UUID、plugin_id、host_id、scope、artifact_digest、desired_enabled、actual_state、generation、config_revision、grant_revision、last_error | PostgreSQL plugin_instances；一个实例属于一个宿主及合法 scope |
| CapabilityBinding | binding_id、host_id、capability、scope_key、provider_instance_id、position、revision、activation_state | PostgreSQL plugin_bindings；单提供者能力对 scope 唯一；有序策略使用唯一 position |
| PluginOperation | operation_id UUID、actor_id、action、scope、expected_revision、request_hash、phase、candidate_instance_id、previous_instance_id、deadline_at、error、created_at/updated_at | PostgreSQL plugin_operations；同 ID 同摘要返回同操作，不同摘要冲突 |
| ConfigSnapshot | instance_id、revision、content、content_hash、created_at | 由 Nacos 输入经验证后落库；只保存必要当前/待提交/恢复快照，禁止秘密值 |
| PermissionGrant | grant_id、instance_id、operations、ai/account scope、resource_allowlist、limits、revision、revoked_at | PostgreSQL 或既有授权配置经持久化；申请与实际授权分离，撤销在副作用前重查 |
| ResourceLease | resource_id、instance_id、kind、borrowed、state、deadline、generation | 活动资源在内存 Scope；持久错误摘要用于恢复，不反序列化连接对象 |
| StateHandoff | operation_id、owner_scope、snapshot_uri、checksum、db_watermark、kv_watermarks、pending_work_keys、stage、recovery_instructions | 本地受限暂存目录+数据库元数据；禁止凭据和未授权人物内容 |

关系：Artifact → 多 Instance；Instance → 多 Binding/ResourceLease；Operation 连接候选和原实例；Operation → 可选 StateHandoff；Instance 引用生效 ConfigSnapshot/Grant。scope 至少区分 host、AI、account、session/device，不以插件名代替 ai_id。

## 作用域与数据规则

- Scope 使用结构化字段 `{kind, ai_id?, account_id?, session_id?, device_id?}`，kind 对应必需字段；host 范围不能自动获得所有人物权限。
- 调用请求包含 invocation_id/event_id/run_id、deadline_at、可信 scope/受众和幂等键；由已认证入口及核心归属记录确定。RPC 对方传入的 ai_id 不是授权依据。
- artifact sha256 只是内容核验；generation 是单写者 fencing 值；revision 是条件更新标识。均不得实现插件版本范围、大小比较或历史版本选择。
- PluginInstance 实际状态为 DISCOVERED/LOADED/INITIALIZED/RUNNING/STOPPED/DISPOSED/UNLOADED/FAILED。desired_enabled 独立记录意图；FAILED 带阶段、残留和可执行恢复动作。
- 一个能力范围只允许一个提交的写入实例；候选可预热资源，激活前不得消费、写用户状态或执行外部动作。

## 生命周期和操作事务

```text
load: DISCOVERED/UNLOADED → LOADED
init: LOADED → INITIALIZED
start: INITIALIZED/STOPPED → RUNNING（业务闸门在提交激活后开放）
stop: RUNNING → STOPPED（先关新工作、再排空、最后撤销出站许可）
dispose: INITIALIZED/STOPPED → DISPOSED
unload: LOADED/DISPOSED → UNLOADED
任何部分失败 → FAILED → 补偿清理或受控恢复
```

管理操作阶段为 requested→prepared→quiesced→committed→cleaned/completed；无停写需求可显式跳过 quiesced。失败记录 failed/compensating/needs_recovery。数据库事务同时更新活动绑定、实例代次和 committed；不把多次独立写当原子切换。

同实例及依赖子图按稳定键排序上锁。外部 I/O 前释放数据库事务，恢复时用 operation_id 与 expected_revision 继续。管理租约过期不能自动授权第二个写入者：先确认资源停止/恢复，再提交接管。插件取消失败时不能将 dispose 成功伪造为所有后台代码已结束。

## 现有业务数据归属

| 数据 | 目标所有者/端口 | 迁移必须保留 |
|---|---|---|
| Person、PlatformIdentity、AIAccountBinding、SocialAccount、Conversation、Message | 平台持久层实现核心 Identity/Conversation 端口 | 稳定 ID、首次归属、引用/发送者/受众和消息保留策略 |
| PrivateReplyJob、PrivateContactState、SocialDelivery | 核心私聊/动作协调，平台仓储实现 | 联系人→任务→发送锁顺序、claim_version（既有领取代次）、run_id、发送摘要、unknown 状态 |
| Episode、Atom、memory_documents、Memory KV | Memory 能力；受限状态端口访问固定所有者 | activity 水位、来源、person/self 分离、CAS claim、待合并集合、durable/queue 名 |
| PersonRelationship | relationship 能力；跨插件只通过公开端口 | ai_id+person_id 主归属、现有多维关系和白名单约束 |
| 表情与素材记录 | sticker 能力 | 素材归属、文件引用、评分与使用信息；停用不得删持久文件 |
| Redis 会话、群重复记录 | 共享会话端口，策略插件消费 | AI 作用域、TTL 语义；不把可丢缓存误当长期状态唯一副本 |

首次迁移不移动物理业务表，不改已有 Alembic revision。新增控制表进入平台资源包 migrations，检查实施时实际 Alembic head 后追加，不假定 `0006` 永远是最后一项。插件私有表迁移拥有自己的登记范围，不能导入其他插件 ORM。

## 状态交接与恢复

1. 校验实例范围、权限和候选配置；插件不读取核心/其他插件私有表。
2. 关旧入口、停定时触发、排空已接收工作。Memory 必须覆盖 durable 回调及两类归并任务；私聊必须覆盖扫描和发送确认。
3. 记录数据库与 KV 的实际共同静止点，再导出快照及待完成工作；不宣称二者具有跨系统事务。
4. 候选在隔离暂存范围导入，校验数量、归属、checksum、水位及待完成任务；失败保留原状态并停止切换。
5. 确认旧写入者全部退出，再提交新绑定和代次。无法证明退出时受控重启对应宿主，拒绝并行接管。
6. 提交后出错按本次变更恢复步骤恢复已确认状态与未知动作记录；不自动回放 unknown 发送、不自动把数据库恢复到会丢已确认新数据的旧快照。

卸载仅删除执行资源和安装记录；用户状态、migration 记录和恢复材料仍按既有保留政策保存。删除用户数据不属于本次管理操作。
