# 2026-09-28 插件化与 Kubernetes 配置部署记录

## 交付版本

- 隔离开发分支：`codex/plugin-runtime`，工作树 `D:/ai-love-worktrees/plugin-runtime`。
- 插件实现：`5b6e8ff`；合入本地 `main`：`62efc47`；移除 Nacos 的应用代码：`a78c266`。
- 正式镜像标签：`plugin-k8s-a78c266-20260928`，八个角色分别构建并导入目标节点的 K3s/containerd。
- 后续提交记录实际部署使用的 DNS、面板 NATS 地址、插件状态卷和终止宽限期；这些清单调整不改变镜像内应用代码。
- 原 main 工作区已先行提交并合并，包含群聊白名单与工作时间相关变更。没有推送 Git 远端。

## 生产状态

| 节点 | 当前角色 | 结果 |
| --- | --- | --- |
| core | gptsovits、ops-panel | 运行正常 |
| app | ai-agent、gateway、director、extension-host、mcp、live-edge | 运行正常 |
| edge | 不再承载本次业务 Deployment | 仍为 NotReady，SSH 不可达 |

MCP、工具网关、形象和推流按用户确认迁到 app。独立 avatar/stream Deployment 已移除，由 live-edge 的两个插件承担；离线节点上卡住的旧 Pod 记录已清理。

七个宿主共 17 个插件全部为 `active`，八个业务/面板 Deployment 均就绪，最终检查各 Pod 重启计数为 0。形象、推流和音乐仍沿用项目原有能力边界，不能将插件激活视为已实现真实播放器或 OBS 适配。

NapCat 容器 ID 与启动时间保持不变：本次没有重启或重建 NapCat。数据库、人物定义、白名单、业务数据和配置备份保留。

## 配置与 Nacos 下线

原 15 份配置完整迁入 `ailove-config` ConfigMap 与 `ailove-config-secrets` Secret，新增 `service.live-edge` 继承原推流配置。对 16 份合并后的文档逐一验证 SHA-256，与迁移备份一致。

删除 Nacos Deployment、Service、Nginx 反向代理入口以及 `ailove-secrets` 中五个 Nacos 专用键。Nginx 配置校验通过后 reload。镜像不包含 Nacos SDK，运行环境不再注入 Nacos 变量；所有服务在 Nacos 删除后重新启动并再次通过插件控制面检查。

Kubernetes 配置卷通过真实 `ServiceConfig.load` 验证热更新：临时独立配置从 revision 1 更新到 2，运行中的监听器收到变化，未重启 Pod。验证后移除该配置。生效延迟包含 kubelet 卷同步周期。

部署中发现 app 的集群 DNS 无法解析实际数据库域名。沿生产数据库连接路径确认失败后，改用宿主机 DNS，真实数据库 `SELECT 1` 和网关/智能体启动均恢复。core 面板使用集群 NATS Service 地址，不使用 app 的本地隧道端口。

## 验收

| 检查 | 结果与范围 |
| --- | --- |
| 最终应用代码 pytest | 198 passed，1 skipped，48.96 秒；默认跳过的十分钟负载已在插件分支单独执行 |
| 前端生产构建、Python 静态检查 | 通过 |
| 八个正式镜像 | 插件工厂导入通过，Nacos SDK 不存在 |
| 真实管理 HTTP 链路 | 登录成功；未登录插件列表返回 401；7 个宿主、17 个插件可查询 |
| 管理页面对应操作接口 | 预检、异步停用天气插件、查询完成状态、重新启用全部通过；操作记录在宿主重启后保留 |
| 生产 ConfigMap/Secret | 合并摘要一致；真实挂载卷配置热更新通过 |
| Nacos 删除后的冷启动 | 17 个插件全部激活，管理页面 HTTP 200 |
| 数据库与平台接入 | 数据库连接查询成功，网关连接既有 NapCat；未向真实联系人发送验收消息 |

原插件分支的浏览器、十分钟负载和生命周期压力验证见 [插件验证记录](plugin-validation.md)。本次验收没有发起真实模型、天气、搜索或语音合成付费调用。

## 旧镜像清理

按项目标签及已核实的应用入口识别历史镜像，删除前再次检查容器引用，保留当前发布与在用基础服务。未对其他项目执行全局 prune。

| 存储 | 移除旧镜像数 | 移除旧镜像归档数 |
| --- | ---: | ---: |
| 本地 Docker / 工作区 | 8 | 5 |
| core K3s/containerd | 42 | 9（节点归档） |
| core Docker | 25 | — |
| app K3s/containerd | 57 | 18 |
| 合计 | 132 | 32 |

132 为不同存储中的镜像实例数，包含跨节点重复内容；不把镜像标称大小相加作为实际回收空间。删除后逐项核对清单，所有目标镜像均不存在。core 根分区可用约 26 GiB，app 约 23 GiB。当前版本镜像包、配置备份、数据库备份与数据卷保留。

**未完成项：edge 节点仍离线，无法读取或删除该节点磁盘上的旧镜像。** 节点恢复连接后需要重新盘点其实际容器和镜像再清理；删除 Kubernetes Pod 记录不等于清空远端磁盘。

本次旧应用镜像已按要求删除，不能依赖旧标签直接回滚。若需要恢复旧程序，应从已保留的 Git 提交重新构建，并审查相应配置与数据兼容性。私有部署备份、摘要与清理明细位于本机 `deploy/private/plugin-deploy-20260928`，不提交版本库。
