# Live Edge 运行边界


`LiveEdgeService` 以 `live-edge` 承载 AvatarModule 与 StreamModule，共享 Kubernetes 配置及 Bus。现有入口为 `python -m live.edge_service`，插件边界见 [插件运行时](../docs/plugin-runtime.md)。

## 模块结果

| 模块 | 输入契约 | 职责 |
| --- | --- | --- |
| AvatarModule | avatar.command.> / AvatarCommand | 形象及舞台事件适配 |
| StreamModule | obs.control / StreamControl | OBS 与推流控制适配 |

模块具有各自订阅句柄，停止完成表示句柄已释放；服务状态对应完整模块集合。共享连接归宿主，回复决策归 Agent。现有外部执行范围以具体适配器的回执为准。

service.live-edge 的字段为 instance_addr、obs_ws_url 和 stream_key。真实推流密钥由部署 Secret 提供，源码及公开配置承载引用或模板。
