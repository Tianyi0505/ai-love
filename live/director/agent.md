# Director 运行边界


现有入口为 `python -m live.director.director_service`。Director 的 session_id 来自 service.director，阵容与发言间隔来自 director.<session_id>。

## 分派结果

live.events 的互动对应明确 session_id、target_ai_id 和 active_actors，目标主题为 agent.live.{ai_id}。合法目标属于场次 actors；Agent 消费具有可信归属的事件。

DeterministicDirectorPolicy 的相同输入对应确定的阵容选择。可用 actor 是分派资格，场次诊断记录对应分派状态。主动发言机会由 proactive_interval_sec 决定，现有结果为机会日志；扩展动作采用既有事件契约。

跨服务字段归 shared/contracts/live.py，Gateway、Director 与 Agent 具有一致的输入输出形状。
