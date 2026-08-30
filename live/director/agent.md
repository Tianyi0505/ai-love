### Agent System

**Director Service** (`live/director/director_service.py`):

- 进程入口是 `python -m live.director.director_service`；`DirectorService` 继承 `BaseService`，以 `director` 注册到 Nacos。
- 服务读取 `service.director` 中的 `session_id`，再加载对应的 `director.<session_id>` 场次配置；场次里的 actors 是允许被调度的 AI 集合。
- Director 订阅 `live.events`，为每个互动选择目标 AI，写入 `session_id`、`target_ai_id` 和 `active_actors`，再发布到 `agent.live.{ai_id}`。Agent 只消费已经完成归属的事件。

**Deterministic Policy** (`live/director/deterministic_director_policy.py`):

- `DeterministicDirectorPolicy` 是当前唯一阵容选择策略；选择结果必须来自场次 actors，不能使用事件里未经验证的目标覆盖导演结果。
- 没有可用 actor 时记录告警并丢弃分发。策略变化应保持相同输入得到可测试的确定结果，除非产品明确引入随机或模型导演。
- 主动发言由场次的 `proactive_interval_sec` 调度；当前 `_proactive_opportunity()` 仅记录机会，扩展时应通过既有事件/契约链路触发，而不是直接调用 Agent 内部对象。

**Runtime Configuration**:

- `service.director`：服务实例地址与 `session_id`。
- `director.<session_id>`：actors 列表和主动发言间隔。
- 直播事件契约位于 `shared/contracts/live.py`；跨服务字段变化必须同步 Gateway、Director 与 Agent。
