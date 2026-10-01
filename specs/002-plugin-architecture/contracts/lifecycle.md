# 当前插件生命周期与 worker 契约

## 实例结果

entry point 分组为 `ai_love.plugins`，工厂为零参数 `create_plugin()`，返回纯实例对象。明确 replace 操作登记候选产物。

| 入口 | 输出 | 完成含义 |
| --- | --- | --- |
| load(verified_artifact) | handle | 已核验工厂和执行环境 |
| init(context) | PreparedCapabilities | 配置、资源及声明能力就绪 |
| start(activation) | Ready | 实例健康与待激活资源就绪 |
| stop(request) | DrainReport | inflight、pending、unknown 和停止状态明确 |
| dispose() | DisposeReport | released_count 与 residual_resources 明确 |
| unload(handle) | UnloadReport | logical_unloaded、process_exited、restart_required 与 residuals 明确 |

Context 包含 instance_id、scope、只读 config、ScopedCapabilities、ResourceScope、ScopedStore、EventPort、Clock 与 Telemetry。管理器拥有绑定提交权，业务写入资格以持久活动代次为依据。

StopRequest 包含 operation_id、deadline_at、reason、mode。停用结果对应执行资源回收，移除结果保留用户数据，maintenance-stop/start 适用于明确实例状态。

## 调用结果

InvocationContext 包含 invocation_id、event_id/run_id、deadline_at、人物、账号、会话、audience、binding_generation、grant_revision 和 idempotency_key，身份由可信入口注入。

成功形状为 `{ok:true,data:...}`，其他状态形状为 `{ok:false,error:{code,message,retryable,side_effect_status,correlation_id}}`。side_effect_status 采用 none、committed、unknown。当前结果码包括 manifest_invalid、config_invalid、dependency_missing、dependency_conflict、permission_denied、scope_mismatch、isolation_unavailable、capability_unavailable、unsupported、timeout、overloaded、provider_failed、side_effect_unknown、lifecycle_failed、drain_timeout、cleanup_incomplete、state_transfer_failed、migration_failed。

所有子调用共享 deadline。只读恢复预算最多 2 次，业务恢复资格由副作用确认状态决定。能力及授权资格以当前活动范围为准。

## Worker 数据协议

- stdin/stdout 使用 4 字节大端长度及 UTF-8 JSON，每帧默认至多 1 MiB。
- Envelope 为 `{id,kind,method,instance_id,generation,payload}`，kind 为 request/response/event/cancel。
- 方法集合由生命周期、健康及声明能力确定。
- request/response 共享 id，流具有 stream_id、sequence 和 end/error 终态。
- 双向端口调用具有独立接收与处理任务，流内顺序由 sequence 确定。
- 大媒体及快照通过授权 ResourceRef 传输。
- 初始配置、身份与会话令牌归受管管道，stdout 归协议，stderr 归脱敏日志。
- 进程身份由宿主句柄确定，启动参数为批准解释器和参数数组。
- EOF、帧校验及预算结果对应明确 worker 状态和资源回收凭证。

## 资源与交接

订阅完成状态包含底层 unsubscribe/drain 和 pump 结束，作业以 instance_id 为范围，共享连接归宿主。StateTransfer 的 prepare/export/import/verify/complete 结果包含 owner、资源引用及联合水位。

进程内代码生效采用声明的 host-restart，worker 的物理回收依据进程树结束。排空期间已接收工作具有适用出站资格，当前安全授权优先于排空资格。
