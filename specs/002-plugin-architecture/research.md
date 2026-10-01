# 独立插件设计依据

**日期**：2026-09-15。依据为当时工作区静态结构及官方协议资料，指标采用目标值。

| 决策 | 适用理由与结果 |
| --- | --- |
| 单一当前契约 | 独立替换以公开行为和 schema 为标准 |
| 独立 wheel 与依赖 | 每个实际插件具有独立代码、清单、资源和锁 |
| 通用宿主 | role、清单、资源端口提供统一运行边界 |
| 可撤销能力租约 | 活动范围及当前代次决定执行资格 |
| ResourceScope | 任务、作业、订阅、HTTP 和文件句柄具有完整资源归属 |
| worker IPC | 独立解释器、JSON 值对象和受管资源代理 |
| 可信进程内 | Memory 与轻量策略保持同进程，代码生效采用宿主维护窗口 |
| 私聊账本 | 固定 run_id、目标、摘要及平台状态保留 |
| Memory 交接 | PostgreSQL、KV、consumer 共同静止水位具有恢复依据 |
| 声明式 UI | 固定外壳与受限贡献共同表达当前能力 |
| 工具方向 | tool-mcp-bridge 提供客户端，统一 MCP 宿主提供服务端 |
| 正式产物验收 | 宿主与公开业务入口提供实际安装证据 |

音乐、形象和推流沿用当时的指令记录与事件回调范围，外部执行成功以实际平台回执为依据。

## 官方资料

- [PyPA 插件发现](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)
- [Python importlib 的代码生效语义](https://docs.python.org/3.11/library/importlib.html#importlib.reload)
- [NATS KV 条件更新](https://docs.nats.io/learn/key-value/)
- [PostgreSQL 显式锁](https://www.postgresql.org/docs/current/explicit-locking.html)
