# 直播合并服务设计结果

`LiveEdgeService` 是 `live-edge` 的统一运行边界，同进程承载 `AvatarModule` 和 `StreamModule`。两个模块共享一个 Bus、配置来源及遥测生命周期。

| 能力 | 结果 |
| --- | --- |
| 运行入口 | live/edge_service.py，python -m live.edge_service |
| 形象模块 | live/avatar/avatar_module.py，avatar.command.> 事件处理 |
| 推流模块 | live/stream/stream_module.py，obs.control 事件处理 |
| 生命周期 | 模块资源具有确定的拥有者，停止结果包含订阅释放 |
| 初始化完整性 | 服务运行状态对应完整模块集合，资源清理覆盖已取得的句柄 |
| 配置模型 | LiveEdgeSettings，对应 service.live-edge |
| Docker | 单一 live-edge target |
| Compose / Kubernetes | 单一 live-edge 运行单元 |
| 网络与存储 | host network、8081 端口和持久数据目录 |

节点归属以实际部署清单为准。模块验收覆盖共享 Bus、各自订阅、完整资源释放及服务级生命周期唯一性。实际交付边界见 [插件运行时](plugin-runtime.md)。
