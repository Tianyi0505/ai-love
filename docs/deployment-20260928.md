# 2026-09-28 插件化与 Kubernetes 配置交付结果

本页的运行数据对应 2026-09-28 验收时点。2026-09-30 的 core 部署结果见 [人设与 MCP 结果](persona-memory-and-mcp-output.md)。

## 交付版本

| 产物 | 标识 |
| --- | --- |
| 插件实现 | 5b6e8ff |
| main 合并 | 62efc47 |
| Kubernetes 配置应用代码 | a78c266 |
| 八个角色正式镜像 | plugin-k8s-a78c266-20260928 |

## 验收状态

core 承载 gptsovits、ops-panel；app 承载 ai-agent、gateway、director、extension-host、mcp、live-edge。七个宿主的 17 个插件全部 active，八个业务/面板 Deployment 就绪，Pod 重启计数为 0。

Avatar、Stream 由 live-edge 的两个插件承载。音乐能力为指令记录；形象和推流能力沿用当时的事件处理范围。NapCat 容器 ID、启动时间及登录态保持原值。数据库、人物定义、白名单、业务数据和配置备份完整保留。

## 配置结果

`ailove-config` ConfigMap 与 `ailove-config-secrets` Secret 承载 16 份合并文档，包括继承推流配置的 `service.live-edge`。各文档 SHA-256 与迁移备份一致。应用镜像采用 Kubernetes 配置读取能力。

真实配置监听记录 revision 1 至 2 的变化，热更新期间 Pod 持续运行。app 使用宿主机 DNS 和基础服务隧道，core 面板使用集群 NATS 地址；真实数据库 `SELECT 1` 成功。

| 验收项 | 结果与环境 |
| --- | --- |
| 应用代码 pytest | 198 passed，1 skipped，48.96 秒 |
| 十分钟负载 | 插件分支独立验收通过 |
| 前端构建与 Python 静态检查 | 通过 |
| 八个正式镜像 | 插件工厂导入通过 |
| 管理 HTTP | 登录成功；鉴权边界返回 401；7 个宿主、17 个插件可查询 |
| 天气插件操作 | 预检、异步停用、状态查询和启用通过 |
| 操作持久化 | 宿主重启后操作记录保留 |
| ConfigMap/Secret | 合并摘要一致，真实挂载卷热更新通过 |
| 冷启动 | 17 个 active 插件，管理页面 HTTP 200 |
| 数据库与平台 | 数据库查询成功，网关连接既有 NapCat |

验收范围为本地回归、生产控制面、配置、数据库连接及平台连接。浏览器和负载证据见 [插件验证结果](plugin-validation.md)。

## 存储结果

| 存储 | 历史镜像回收数 | 历史归档回收数 |
| --- | ---: | ---: |
| 本地 Docker / 工作区 | 8 | 5 |
| core K3s/containerd | 42 | 9 |
| core Docker | 25 | — |
| app K3s/containerd | 57 | 18 |
| 合计 | 132 | 32 |

132 表示各存储中的镜像实例总数。验收时 core 根分区可用约 26 GiB，app 约 23 GiB。当前发布镜像、基础服务、配置备份、数据库备份和数据卷保留。存储核验范围为本地、core 和 app。

恢复材料包含保留的 Git 提交及对应配置、数据备份。私有明细位于 `deploy/private/plugin-deploy-20260928`。
