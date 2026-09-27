### Agent System

**Live Edge Service** (`live/edge_service.py`):

- 进程入口是 `python -m live.edge_service`；`LiveEdgeService` 继承 `BaseService`，以 `live-edge` 使用 Kubernetes 挂载配置，并在一个 edge 侧进程内组合 avatar 与 stream。
- 模块按 `AvatarModule`、`StreamModule` 顺序启动，按相反顺序停止。任一模块启动失败时必须清理已经启动的模块，不能留下部分可用的 edge 进程。
- `live-edge` 是部署边界；`live/avatar` 与 `live/stream` 是进程内模块，不应恢复成独立服务或各自创建 NATS 连接。

**Avatar Module** (`live/avatar/avatar_module.py`):

- 订阅 `avatar.command.>` 并处理 `AvatarCommand`。模块使用宿主注入的共享 Bus，保存 subscription，并在 `stop()` 中显式 unsubscribe。
- Avatar 负责形象和舞台事件适配，不承载 Agent 回复决策。

**Stream Module** (`live/stream/stream_module.py`):

- 订阅 `obs.control` 并处理 `StreamControl`。OBS WebSocket 地址和推流密钥来自 `LiveEdgeSettings`，不写入源码或日志。
- Stream 负责 OBS/推流控制；新增真实适配器时保留模块生命周期和共享 Bus 边界。

**Runtime Configuration** (`service.live-edge`):

- `instance_addr`：Kubernetes 挂载配置 注册地址。
- `obs_ws_url`：OBS WebSocket 地址。
- `stream_key`：推流密钥；只能通过部署环境注入 Kubernetes 挂载配置 模板值，不能提交真实值。
