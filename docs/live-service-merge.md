# 直播 edge 服务合并改造清单

## 服务入口

- 新增 `live/edge_service.py`，以 `live-edge` 名称启动一个 `BaseService`。
- 将 `live/avatar/avatar_service.py` 改为 `live/avatar/avatar_module.py`，入口类改为 `AvatarModule`。
- 将 `live/stream/stream_service.py` 改为 `live/stream/stream_module.py`，入口类改为 `StreamModule`。
- `LiveEdgeService` 创建两个模块并向其注入同一个 Bus。
- 启动顺序设为 avatar、stream；停止和启动失败清理顺序设为 stream、avatar。
- 两个模块保存 NATS subscription，并在 `stop()` 中取消订阅。

## 配置

- 将 `StreamSettings` 改为 `LiveEdgeSettings`。
- 将 Nacos 配置 `service.stream.yaml` 改为 `service.live-edge.yaml`。
- 从 Nacos 初始化脚本移除 `avatar`、`stream`，加入 `live-edge`。

## 部署

- 将 Dockerfile 的 avatar、stream target 合并为 `live-edge` target，入口设为 `python -m live.edge_service`。
- 将 Docker Compose 和本地 Compose 的 avatar、stream 服务合并为 `live-edge`。
- 将 Kubernetes 的 avatar、stream Deployment 合并为 `live-edge` Deployment。
- 将 live-edge 调度到 edge 节点，使用 host network，暴露 8081 端口并挂载数据目录。
- 更新 README 的部署单元和目录说明。

## 验证

- 验证两个模块共享 Bus，并分别订阅 `avatar.command.>` 与 `obs.control`。
- 验证模块停止时取消订阅。
- 验证 stream 启动失败时清理已启动的 avatar 模块。
- 验证服务只执行一次 Bus、Nacos 和 telemetry 生命周期。
