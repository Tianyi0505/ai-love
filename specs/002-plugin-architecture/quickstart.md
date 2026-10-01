# 独立插件目标验收环境

本文定义 31 包目标设计的验收条件与入口。现有实现入口见 [插件运行时](../../docs/plugin-runtime.md)。

## 环境结果

Python 3.11、PowerShell、Docker、Node/npm，独立本地 PostgreSQL、NATS JetStream、Redis、配置 fixture 和模拟平台。Compose project 为 ailove-plugin-test，端口归环回地址，测试库名称以 `_test` 结尾。

独立产物包含核心、平台、宿主、31 插件和依赖 wheelhouse。凭据采用受限测试文件，核心验收由仓库外 cwd 的正式安装包提供。

## 目标入口与产物

| 目标入口 | 产物或结果 |
| --- | --- |
| scripts/plugins/prepare-local.ps1 | 本地配置、连接和受限凭据 |
| deployment/local/compose.plugins.yml | 独立验收服务 |
| scripts/plugins/build-artifacts.ps1 | wheel、清单、schema、锁与 SHA-256 |
| scripts/plugins/test-installed-artifacts.ps1 | 正式安装包及空插件宿主证据 |
| scripts/plugins/test-conformance.ps1 | 指定插件或全目录的六项变更及 100 次启停证据 |
| scripts/plugins/test-recovery.ps1 | 数据库、KV、consumer 与动作凭证的恢复结果 |
| scripts/plugins/test-load.ps1 | Persons、Conversations、EventsPerSecond、DurationSeconds 对应指标 |
| 前端 test:plugins | 同一静态构建中的贡献、鉴权和撤销结果 |

目标脚本的实现状态由 [tasks.md](tasks.md) 表达。现有回归入口为 tests/test_model_failover.py、tests/test_live_edge_service.py、tests/test_private_reply_flow.py、tests/test_social_delivery_recovery.py 和 tests/test_memory_state.py。

## 通过标准

- 空插件宿主提供管理、鉴权、诊断和准确业务 readiness。
- 语音最小场景通过正式宿主返回合法 AudioReference。
- QQ 场景包含实际 WS/HTTP 协议模拟与 NATS，Memory 场景包含真实持久活动和调度。
- 每个实际包的添加、移除、替换、启用、停用和升级具有独立证据。
- 100 次启停资源回到基线，联合恢复 ≤5 分钟，已确认状态 RPO=0。
- 2 AI、20 会话、每秒 10 事件、900 秒，P95 增量 ≤max(基线×10%,20ms)，模型调用和 token 量至多为基线。

产物资料位于 output/plugin-architecture，包含机器、依赖、摘要、操作 ID、修订、水位和具体环境范围。目标标准见 [acceptance.md](acceptance.md)。
