# 插件重构验证结果

**验收日期**：2026-09-27 至 2026-09-28。**环境**：Windows / Python 3.11，本地 PostgreSQL/pgvector、NATS 与平台/模型替身。分支为 `codex/plugin-runtime`，工作树为 `D:/ai-love-worktrees/plugin-runtime`。

本页对应插件分支合并验收。main 的 198 passed、1 skipped 及生产部署证据见 [2026-09-28 交付结果](deployment-20260928.md)。

| 验收项 | 结果 | 覆盖范围 |
| --- | --- | --- |
| 完整 pytest | 187 passed，1 skipped，58.76 秒 | 本地数据库与总线；长负载独立验收 |
| 十分钟私聊负载 | 1 passed，600.032 秒 | 10 会话、每秒 1 条、600 条、真实数据库与边界替身 |
| Avatar 连续启停 | 100 轮通过 | 真实 NATS 控制与订阅资源基线 |
| MCP 工具启停 | 通过 | 真实 HTTP 发现、调用与目录状态 |
| 工具变化传播 | 通过 | MCP HTTP、网关授权、类型化总线与 Agent 工具图 |
| 管理 API | 通过 | 401/403 鉴权与同源边界、预检、异步操作和状态 |
| 新插件示例 | 通过 | uninstalled、安装、启用、调用、移除和清单诊断 |
| 生命周期契约 | 通过 | 依赖、级联、幂等、修订、重启、排空和清理结果 |
| 前端构建 | 通过 | TypeScript 与 Vite 生产构建 |
| 静态检查 | 通过 | Ruff、compileall、5 份 YAML 与 git diff --check |
| 浏览器 | 通过 | Playwright、登录、插件操作、桌面与 390×844 布局 |

## 负载数据

```json
{
  "duration_seconds": 600.032,
  "messages": 600,
  "sent": 600,
  "platform_requests": 600,
  "unique_runs": 600,
  "model_calls": 600,
  "model_calls_per_message": 1.0,
  "p95_seconds": 0.103
}
```

数据适用于本地私聊处理链，模型与平台发送采用替身。外部供应商和生产硬件指标采用各自环境的独立证据。

## 验收入口

```powershell
$env:AILOVE_TEST_DATABASE_URL = '<本地测试 PostgreSQL 的 asyncpg URL>'
$env:AILOVE_TEST_NATS_URL = 'nats://127.0.0.1:14223'
python -m pytest tests -q --tb=short -rs
```

长负载的启用条件为 `AILOVE_RUN_PRIVATE_REPLY_LOAD=1`，入口为 `python -m pytest tests/test_private_reply_load.py -q -s`。前端构建入口为 `npm --prefix admin/console/frontend run build`。

浏览器验收环境包含生产路由、真实 NATS 宿主、编译后的前端及内存登录存储。生命周期机制使用专用验收插件。日志位于 `output/plugin-validation/`，截图位于 `output/playwright/`，运行资料归本地验收产物。
