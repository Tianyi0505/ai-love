# Kubernetes 配置结果

配置来源为 Kubernetes 挂载卷。普通业务字段、敏感覆盖和连接凭据各有明确资源归属。

| 资源 | 容器目录 | 内容 |
| --- | --- | --- |
| ConfigMap ailove-config | /app/config | 配置标识.yaml 格式的公开 YAML 文档 |
| Secret ailove-config-secrets | /app/config-secrets | 同名文档的敏感字段覆盖 |
| Secret ailove-secrets | 进程环境 | 数据库、模型和外部服务凭据 |

配置标识包含 `agent.default`、`agent.<ai_id>`、`agent.catalog`、`ailove.config` 和 `service.*`。Secret 对象递归覆盖 ConfigMap，列表整体替换。真实凭据由 Secret 及私有部署资料承载，公开参考模板位于 `deploy/config`。

## 资源产物

`deploy.render_config` 的产物为 ConfigMap 和 Secret。密码、token、密钥、带凭据 URL，以及含敏感值的列表归 Secret；自定义敏感字段的归属由交付核验确认。私有资源文件位于 `deploy/private`。

```powershell
python -m deploy.render_config --source deploy/private/config --output deploy/private/runtime-config.yaml
kubectl apply -f deploy/private/runtime-config.yaml
```

挂载单位为完整目录。应用每两秒读取最新文件，配置生效时间包含 kubelet 卷同步周期。生效快照符合业务校验，监听器保留最近成功状态，诊断信息采用脱敏内容。

人物定义、工具发现和配置监听采用现有运行规则。配置监听属于插件资源作用域。应用交付保留线上配置、白名单、人物定义、密钥和业务数据。

## 本地环境

```powershell
$env:AILOVE_CONFIG_DIRECTORY = 'deploy/config'
$env:AILOVE_CONFIG_SECRET_DIRECTORY = 'deploy/private/config-secrets'
$env:AILOVE_CONFIG_POLL_INTERVAL_SEC = '2'
python -m plugin_runtime --role live-edge
```

服务配置包含对应模型要求的字段。生产敏感字段由挂载 Secret 提供，业务权限以挂载资源为范围。

## 部署状态

2026-09-28 的配置交付结果为 16 份合并文档 SHA-256 与备份一致，真实 `ServiceConfig.load` 监听收到 revision 1 至 2 的更新。

2026-09-30 的 core 部署使用 `ClusterFirstWithHostNet` 和集群 NATS Service。各宿主将 `/opt/ailove/data/plugins` 挂载到 `/app/plugin-state`，`AILOVE_PLUGIN_STATE_DIR` 指向状态目录；每个角色拥有独立 SQLite 日志与文件锁。Pod 终止宽限期为 180 秒。

历史部署数据见 [2026-09-28 部署结果](deployment-20260928.md)，core 状态见 [人设与 MCP 结果](persona-memory-and-mcp-output.md)。
