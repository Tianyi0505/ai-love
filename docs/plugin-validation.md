# 插件重构验证记录

验证日期：2026-09-27 至 2026-09-28，Windows / Python 3.11。本地隔离 worktree：`D:/ai-love-worktrees/plugin-runtime`；分支：`codex/plugin-runtime`。

## 结果

| 检查 | 结果 | 覆盖与限制 |
| --- | --- | --- |
| 完整 pytest | 187 passed，1 skipped，58.76 秒 | 使用本地 PostgreSQL/pgvector 与 NATS；默认跳过的十分钟测试已另行执行 |
| 十分钟私聊持续负载 | 1 passed，600.032 秒 | 10 个会话、每秒 1 条、共 600 条，真实数据库，模型与平台发送为替身 |
| 内置 Avatar 插件连续启停 | 100 轮通过 | 真实 NATS 控制请求；每次停用订阅回到仅控制面、启用后恢复业务订阅 |
| MCP 工具启停 | 通过 | 真实 HTTP MCP：发现、调用、撤销后列表消失且调用失败、启用后恢复 |
| 工具变化传递到已有智能体 | 通过 | MCP HTTP → 工具网关授权 → 类型化总线 → load_toolset → generate_plan；仅配置存储和模型执行被替换 |
| 管理 API | 通过 | 未登录 401、跨站变更 403、预检、异步操作、同一运行时状态 |
| 新插件交付示例 | 通过 | 运行中刷新，保持未安装；安装后启用并实际调用；移除后订阅撤销；坏清单独立报告 |
| 生命周期契约 | 通过 | 依赖拓扑与级联、缺失/循环依赖、幂等、修订冲突、重启恢复、排空、失败清理与重试 |
| 前端构建 | 通过 | TypeScript 编译和 Vite 生产构建 |
| 静态检查 | 通过 | 变更 Python 文件 Ruff、新增模块 compileall、5 份部署 YAML 解析、git diff --check |
| 浏览器 | 通过 | Playwright 操作生产构建，登录与插件启停；桌面和 390×844 手机布局 |

完整测试唯一警告来自现有 nacos 依赖的 Pydantic class Config 弃用提示。

## 负载测量

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

此结果验证已有私聊生产处理链在真实数据库上的回归，不代表真实模型、QQ 网络或生产硬件延迟；没有向任何真实联系人发送消息。

## 重现

准备隔离本地 PostgreSQL/pgvector 与 NATS，并设置连接：

```powershell
$env:AILOVE_TEST_DATABASE_URL = '<本地测试 PostgreSQL 的 asyncpg URL>'
$env:AILOVE_TEST_NATS_URL = 'nats://127.0.0.1:14223'
python -m pytest tests -q --tb=short -rs

$env:AILOVE_RUN_PRIVATE_REPLY_LOAD = '1'
python -m pytest tests/test_private_reply_load.py -q -s
Remove-Item Env:AILOVE_RUN_PRIVATE_REPLY_LOAD
```

```powershell
Set-Location admin/console/frontend
npm ci
npm run build
```

浏览器使用本地验证 harness：生产路由、真实 NATS 插件宿主与编译后的前端，登录凭据存储是内存测试实现，外部业务插件停用。不会把这个验证页面视为生产部署。

本地日志位于 `output/plugin-validation/`，截图位于 `output/playwright/plugins-desktop.png` 与 `plugins-mobile.png`；这些运行产物不提交版本库。插件生命周期中的失败注入测试使用专门测试插件验证框架契约，不据此声称已有真实业务存在对应故障。

未执行生产 Nacos 配置变更、真实 QQ/天气/搜索/语音外部调用、镜像发布或部署。未验证不可信代码沙箱、跨机器主从切换、Python 模块无损热升级；这些不属于当前实现能力。
