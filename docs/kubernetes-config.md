# Kubernetes 配置

配置统一来自 Kubernetes 挂载卷，不运行 Nacos，不依赖 Nacos SDK，也不向配置服务注册运行实例。

| 资源 | 容器目录 | 内容 |
| --- | --- | --- |
| ConfigMap `ailove-config` | `/app/config` | 普通 YAML 文档，每个 data key 为 `配置标识.yaml` |
| Secret `ailove-config-secrets` | `/app/config-secrets` | 同名文档的敏感字段覆盖层 |
| Secret `ailove-secrets` | 现有环境变量 | 数据库、模型和外部服务凭据 |

例如 `agent.default.yaml`、`agent.ai_luoyu.yaml`、`agent.catalog.yaml`、`ailove.config.yaml`、`service.gateway.yaml`。配置键和原来的业务模型一致；Secret 的字典递归覆盖 ConfigMap，列表整体替换。不要把凭据复制进普通 ConfigMap。

## 生成与交付

`deploy/config` 保存无真实凭据的参考模板。部署前准备私有配置目录，检查值后生成资源：

```powershell
python -m deploy.render_config --source deploy/private/config --output deploy/private/runtime-config.yaml
kubectl apply -f deploy/private/runtime-config.yaml
```

生成器分离密码、token、密钥字段以及带凭据的连接 URL；含敏感字段的列表整体移入 Secret。请检查生成结果，特别是自定义、非标准字段名。生成文件包含明文 Secret 输入，不提交版本库。

运行部署引用这两个资源。卷必须挂载整个目录，**不使用 subPath**；应用每两秒重新打开配置文件，能够观察 kubelet 的原子目录切换。实际生效时间还包括 Kubernetes 的卷同步时间。配置无效或回调失败时，监听器保留上一份成功状态并重试，不记录配置内容。

修改配置可通过 `kubectl edit configmap ailove-config -n ailove` 或 Kubernetes Dashboard。敏感字段使用 Secret。修改普通配置和敏感覆盖时，应保持两者在同步期间也满足业务校验。

业务实例仍由现有人物存储与配置决定；已有配置监听、定时刷新和下一轮工具发现逻辑继续工作。停用插件时其配置监听随资源作用域移除。

## 本地运行

```powershell
$env:AILOVE_CONFIG_DIRECTORY = 'deploy/config'
$env:AILOVE_CONFIG_SECRET_DIRECTORY = 'deploy/private/config-secrets'
$env:AILOVE_CONFIG_POLL_INTERVAL_SEC = '2'
python -m plugin_runtime --role live-edge
```

敏感覆盖目录可省略，但配置必须包含服务要求的字段。生产必须挂载对应 Secret。程序不调用 Kubernetes 管理 API，不需要为业务插件授予读取整个命名空间 Secret 的 RBAC 权限。

## 迁移顺序

1. 备份现有配置、Deployment 和镜像引用。
2. 分离公开与敏感值，校验合并结果与备份一致；新增 `service.live-edge` 继承原 `service.stream`。
3. 创建 Kubernetes 配置资源，部署使用挂载配置的镜像；保留原有白名单、人物定义、密钥和业务数据。
4. 验证全部插件宿主、管理页面、配置热更新和实际依赖连接。
5. 停用并删除 Nacos Deployment/Service 和反向代理入口；原备份保留供审计与恢复。

配置模板不会自动覆盖线上已有配置。部署应用更新时不要重新渲染或初始化生产配置。

## 当前跨云部署约束

app 节点的业务 Pod 使用 `hostNetwork` 和 `dnsPolicy: Default`，沿用宿主机的 DNS 与现有基础服务隧道；NATS 地址为 `nats://127.0.0.1:14222`。该节点不能可靠访问集群 DNS，改为 `ClusterFirstWithHostNet` 会导致生产数据库域名解析失败。

core 节点上的语音服务和管理面板使用 `ClusterFirstWithHostNet`，通过 `nats://nats:4222` 访问集群 Service。不要把 app 节点的隧道端口直接复制到 core。

七个插件宿主将 `/opt/ailove/data/plugins` 挂载到 `/app/plugin-state`，以 `AILOVE_PLUGIN_STATE_DIR` 指定状态目录。各角色使用独立 SQLite 日志与文件锁；更换 Pod 后保留插件目标状态和操作记录。终止宽限期为 180 秒，留出插件排空和资源释放时间。

本次生产迁移与清理结果见 [2026-09-28 部署记录](deployment-20260928.md)。
