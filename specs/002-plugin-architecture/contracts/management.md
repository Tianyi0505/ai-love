# 管理、配置与声明式 UI 契约

管理 API 位于既有前缀的 `/plugins`，身份来自 require_session；CLI 采用受限 credentials-file。批准的本地产物及持久操作记录决定变更范围。

## HTTP 结果

| Method / Path | 输入 | 输出 |
| --- | --- | --- |
| GET /plugins | host_id 可选 | 目录、实例、能力和摘要 |
| GET /plugins/instances/{id} | 实例 ID | scope、目标/实际状态、代次、修订与健康 |
| POST /plugins/preflight | action、host、instance/artifact、scope、config、bindings、expected_revision | 影响范围、依赖、配置、重启要求及执行资格 |
| POST /plugins/operations | operation_id、action、host、expected_revision、目标字段、stop_dependents | 202 与 operation_id/status_url |
| GET /plugins/operations/{id} | 操作 ID | 阶段、结果、恢复资料和影响范围 |
| PUT /plugins/instances/{id}/config | operation_id、expected_revision、content | 202 与有效配置状态 |
| PUT /plugins/instances/{id}/grants | operation_id、expected_revision、grants | 202 与当前授权状态 |
| GET /plugins/contributions | 当前身份与 scope | 有效贡献和目录修订 |
| POST /plugins/contributions/{id}/query | query_ref 与参数 | 授权数据或 410 撤销状态 |
| POST /plugins/contributions/{id}/action | operation_id、action_ref、参数 | 授权结果或操作引用 |

action 集合为 install、enable、disable、replace、remove、stop、start，upgrade 对应 replace。install 登记已交付产物，首次 expected_revision=0，其余值对应当前修订。重复 operation_id 与相同摘要返回原操作。

HTTP 401、403、404、409、410、422、503 具有各自身份、范围、对象、修订、贡献、字段及控制状态语义。202 是操作接收凭证，completed 是执行完成凭证。依赖消费者的停用范围由 stop_dependents 显式决定。

## CLI 目标入口

`python -m ailove_host.cli --endpoint <approved-host> --credentials-file <path> plugins <command>`。

list/status 提供查询，preflight/apply 使用 request-file，operations get 使用 operation ID，各变更具有当前修订和固定操作标识。凭据归受限文件，管理结果归统一控制 API。

## 配置结果

部署条目包含 plugin_id、artifact_ref、enabled、host_role、scope、config_ref、permission_ref 和 bindings。artifact_ref 为批准位置及 sha256，schema 路径归插件目录。

覆盖语义为插件默认、服务及 AI/账号范围，对象递归合并，数组整体替换，标量替换，显式移除标记对应字段集合结果。配置生效依据完整有效快照和修订；热改资格由 schema 声明。

规划时配置来源为 Nacos 默认输入与控制库 override，统一 reconcile 提供当前有效结果。当前部署配置来源见 [Kubernetes 配置](../../../docs/kubernetes-config.md)。

## UI 贡献结果

固定外壳包含登录、概览及插件管理。贡献字段为 contribution_id、instance_id、title、kind、schema、query_ref、action_refs 和 scope，查询及动作引用属于该实例获准能力。

固定路由为 `/extensions/:contributionId/*`，导航来自有效目录，页面采用声明式数据。撤销结果为能力状态和 410，历史诊断归核心管理页。
