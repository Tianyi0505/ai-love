# 当前插件生命周期与 worker 协议

## 工厂与实例

entry point 分组 `ai_love.plugins`，值指向零参数 `create_plugin()` 工厂。工厂只创建对象，不启动任务/连接或外部动作。相同 plugin_id 的替换候选必须以明确 replace 操作登记，普通重复安装拒绝。

Plugin 实现 `async init(context) -> PreparedCapabilities`、`async start(activation) -> Ready`、`async stop(request) -> DrainReport`、`async dispose() -> DisposeReport`。Loader 提供 `load(verified_artifact) -> handle` 和 `unload(handle) -> UnloadReport`。管理器维护状态，不允许插件自行提交绑定。

Context：instance_id、scope、只读 config、ScopedCapabilities、ResourceScope、ScopedStore、EventPort、Clock、Telemetry。必须与现有私有 host/DB/bus 客户端解耦。资源创建通过 Scope，init 可准备资源但不能消费事件或写用户数据。

PreparedCapabilities：提供能力名、允许方法与健康说明；必须为清单声明的子集。Ready：ready 布尔值、诊断与待激活资源。业务激活闸门由管理器在持久提交后开放，start 成功不自授写入许可。

StopRequest：operation_id、deadline_at、reason、mode=drain/cancel。DrainReport：inflight_remaining、pending_work_refs、unknown_actions、stopped。DisposeReport：released_count、residual_resources。UnloadReport：logical_unloaded、process_exited、restart_required、residuals。存在残留不得返回成功完成卸载。

`enabled=false` 映射 stop→dispose→unload；remove 另撤销安装记录和包文件，保留用户数据。显式 maintenance-stop/start 可复用已停止对象；部分失败只能补偿/重新加载，不自动从失败阶段继续产生业务动作。

## 调用与错误

InvocationContext：invocation_id、event_id/run_id、deadline_at、ai_id、account_id、person_id、conversation_id、audience、binding_generation、grant_revision、idempotency_key。身份从认证入口注入；worker 不能覆写此上下文。取消由 request ID 关联，不能让工具 arguments 指定另一个取消目标。

成功 `{ok:true,data:...}`；失败 `{ok:false,error:{code,message,retryable,side_effect_status,correlation_id}}`。side_effect_status 为 none/committed/unknown。错误码：manifest_invalid、config_invalid、dependency_missing、dependency_conflict、permission_denied、scope_mismatch、isolation_unavailable、capability_unavailable、unsupported、timeout、overloaded、provider_failed、side_effect_unknown、lifecycle_failed、drain_timeout、cleanup_incomplete、state_transfer_failed、migration_failed。不得引入 incompatible_api 或插件版本错误。

调用截止时间贯穿所有子调用；只读默认最多重试两次且总时限不增加。业务动作已 committed/unknown 后不能整体回合重试。能力停止或授权撤销后，新调用和下一项副作用拒绝。

## Worker IPC

- 双向 stdin/stdout：4 字节无符号大端长度 + UTF-8 JSON，默认每帧 ≤1 MiB。音频/图片/大型快照通过受限资源引用传输，不直接撑大帧。
- Envelope：`{id, kind, method, instance_id, generation, payload}`；kind=request/response/event/cancel。方法表由固定生命周期、健康和声明能力组成，不接受任意模块路径或 eval。
- request/response 使用相同 id；event 流有 stream_id/sequence，结束帧显式 end/error。并发响应可乱序，单流 sequence 必须有序。
- 支持宿主→worker 生命周期/能力调用，以及 worker→宿主的已授权端口调用；接收循环不得等待业务处理完成才继续读取，防止嵌套能力请求死锁。
- 配置、身份和初始会话令牌由受管管道传入，不放命令行；stdout 仅协议，stderr 结构化脱敏日志。宿主用创建的进程/管道绑定身份，不能信任 payload 中自报 instance_id。
- 取消只中断可取消计算，发送中的动作取消仍可能 unknown。EOF/畸形帧/超限终止该 worker 的新工作并标记失败；超时后按模式回收进程树。
- 进程使用批准的解释器绝对路径及参数数组启动，不经 shell 拼命令。不继承全量环境；普通 worker 不声称恶意代码隔离。restricted-worker 由受控容器 launcher 限制 UID、网络、卷及 CPU/内存/进程数。

## 资源和持久交接

订阅包装必须同时等待 pump task 结束及底层 unsubscribe/drain 完成；不能只 cancel 一个任务就记录资源归零。定时作业使用 instance_id 前缀，停止只移除该实例作业；共享连接用借用句柄，不能被插件关闭。

状态导出/导入为当前 `StateTransfer` 契约：prepare/export/import/verify/complete，输入包含 operation_id、owner scope、资源引用与水位。它只负责本次状态交接，不支持历史格式自动适配。任何 import/verify 失败均不开放新写入者。

进程内资源无法回收时返回 restart_required；Memory 代码替换统一走 host-restart。停止过程先关入口，排空时仍授予已接收调用必要权限，排空完成才撤销全部出站；安全授权即时撤销优先于排空。
