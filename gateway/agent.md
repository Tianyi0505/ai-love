### Agent System

**Gateway Service** (`gateway/gateway_service.py`):

- 进程入口是 `python -m gateway.gateway_service`；`GatewayService` 继承 `BaseService`，以 `gateway` 使用 Kubernetes 挂载配置，并复用统一的 NATS、调度器与遥测生命周期。
- 启动时读取 `service.gateway` 和 `ailove.config`，连接 PostgreSQL，创建共享 HTTP client，并为每个账号按 `ai_love.channels` entry point 加载平台适配器。新增平台应实现 `Channel` 契约，不应把平台协议分支塞进 Agent。
- Gateway 只负责平台接入、消息归一化、账号归属与投递。图片和语音在这里保留为 URL；理解、生成和回复决策属于 `ai-agent`。

**Message Routing** (`gateway/gateway_message_handler.py`, `gateway/social_router.py`):

- 入站消息先落库并补齐身份、群成员和实体 grounding，再依据数据库中的账号归属发布到 `social.chat.{ai_id}`；直播互动发布到 `live.events`。
- 出站统一通过 `social.send.request` 请求，由 `SocialSendHandler` 路由到原平台账号并写入会话记录。跨服务调用必须继续使用 `shared/contracts/` 中的模型。
- `identity.resolve-people.request`、`history.search-group.request` 与 `social.send.request` 是 Gateway 对外 RPC 边界；修改字段时必须同步生产者、消费者和契约测试。

**QQ and QZone** (`gateway/qq_channel.py`, `gateway/qzone_service.py`):

- `QQChannel` 封装 NapCat WebSocket/HTTP、引用和合并转发补全、内容策略及发送能力。超时来自全局配置，不在调用点另设常量。
- QQ 白名单在启动阶段同步；QQ 空间任务使用账号绑定得到 owner AI，再结合 Agent 行为日程和关系数据决定点赞、评论与回复。

**Runtime Configuration**:

- `service.gateway`：`instance_addr`、账号列表、adapter 和平台连接参数。
- `ailove.config`：QQ 白名单、超时、社交保留期、grounding、关系策略和 QQ 空间调度参数。
- 账号与 AI 的真实归属来自 PostgreSQL；配置里的 `owner_ai_id` 不能代替运行时归属查询。
