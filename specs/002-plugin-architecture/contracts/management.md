# 管理接口、配置和声明式 UI

管理路径位于现有控制台 API 前缀下的 `/plugins`，宿主提供同一应用层控制服务；沿用 `require_session`，命令行凭据通过受限文件读取。接口不接受远程任意代码 URL，不直接写 Nacos/DB 绕过操作日志。

## HTTP 操作

| Method / Path（相对现有 API 前缀） | 请求 | 响应 |
|---|---|---|
| GET /plugins | host_id 可选 | 当前安装条目和实例状态、能力、产物摘要，无插件版本 |
| GET /plugins/instances/{id} | — | scope、期望/实际状态、代次、修订、健康、残留、最后错误 |
| POST /plugins/preflight | action、host_id、instance_id?、artifact_ref?、scope?、config?、bindings?、expected_revision? | 影响范围、缺失能力、配置错误、重启需求、可执行标志；不运行插件代码 |
| POST /plugins/operations | operation_id、action、host_id、expected_revision、instance_id?、artifact_ref?、scope?、config?、bindings?、stop_dependents=false | 202 `{operation_id,status_url}`；只接受具体动作所需字段 |
| GET /plugins/operations/{id} | — | 阶段、完成结果、恢复指引、受影响实例，无凭据正文 |
| PUT /plugins/instances/{id}/config | operation_id、expected_revision、content | 202 操作引用；先验证快照再提交，失败保留当前配置 |
| PUT /plugins/instances/{id}/grants | operation_id、expected_revision、grants | 202；授权独立，不能从插件 config 推导放行 |
| GET /plugins/contributions | 当前登录身份/scope | 当前可用声明式贡献和目录修订 |
| POST /plugins/contributions/{id}/query | 受限 query 引用、参数 | 表格/文档/状态值；撤销后 410 |
| POST /plugins/contributions/{id}/action | operation_id、action 引用、参数 | 经授权的操作结果/引用；不能直接调用任意 URL |

action 限定 install/enable/disable/replace/remove/stop/start；upgrade 在 CLI 作为 replace 的同义入口。install 只登记已经由交付脚本准备的本地产物，不运行 pip。replace 同时传候选 artifact_ref，保持业务范围并按新实例交接。首次 install 的 expected_revision=0，其他操作必须匹配当前管理修订。

错误：401 未登录、403 无权、404 对象不存在、409 修订/幂等摘要/依赖冲突、410 已撤销贡献、422 配置或字段错误、503 持久控制面不可用。重复 operation_id 且同请求摘要返回原操作，不同摘要返回 409。操作返回 202 不代表业务已就绪；调用方必须查询 completed。

禁用唯一必需能力默认 409，响应列出会停用的业务范围；显式 stop_dependents 才执行依赖消费者停用，管理面仍可用。它是产品运维选项，不是要求开发代理再次请求已获准本地操作。

## CLI（实施后提供）

`python -m ailove_host.cli --endpoint <loopback-or-approved-host> --credentials-file <path> plugins <command>`。

- list/status：只读查询；status 要求 `--instance`。
- preflight/apply：`--request-file <json>`，内容为上述请求；apply 只提交，`--wait` 时有界查询至完成。
- install/enable/disable/replace/upgrade/remove：同应用层命令的便捷参数，均携 operation_id/expected_revision。
- operations get：`--operation <id>`。

本地管理测试由 fixtures 登录生成临时凭据文件，不把秘密作为命令参数或显示日志。CLI 不是修改数据库和 Nacos 的后门。

## 配置输入

部署清单的条目包含 plugin_id/artifact_ref/enabled/host_role/scope/config_ref/permission_ref/bindings。artifact_ref 是批准位置+sha256，不是版本。插件专属 schema 存包内相对路径；解析后必须在该包目录内，拒绝路径穿越。

配置顺序为插件默认→服务→AI/账号覆盖：对象递归、数组整体替换、标量替换、显式移除标记删除字段。字段热改由插件当前 schema 属性声明；不支持热改时执行受控替换。配置修订只用于乐观并发和快照，禁止用于兼容协商。

持久操作、绑定、Nacos 输入通过单一 reconcile 路径汇合。外部 Nacos 更新要经同样验证和修订检查；管理接口在本轮不隐式发布 Nacos，新配置生效源及回写策略在部署清单中明确。首期管理变更保存宿主控制库的显式 override，Nacos 是默认输入；移除 override 后重新采用当前 Nacos 值，不由周期轮询覆写管理操作。

## UI 贡献

固定外壳保留登录、概览和插件管理。贡献描述包含 contribution_id、instance_id、title、kind、schema、query_ref、action_refs、scope；服务端验证所有引用属于该实例获准能力。业务导航从目录生成，前端不 import 具体插件 JS。

停用撤销贡献和可执行动作，旧页面显示“能力已停用”并退出可操作状态。历史诊断仍留在核心管理页。记忆与人物视图迁到公开查询端口，不继续从后端 app.state 暴露具体插件 reader。
