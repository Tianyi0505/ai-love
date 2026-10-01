# Implementation Plan: 独立插件产物设计

**Branch**: main | **Date**: 2026-09-15 | **Spec**: [spec.md](spec.md)
**Status**: 目标设计与任务结构已定义。当前交付边界见 [插件运行时](../../docs/plugin-runtime.md)。

## Summary

目标结构由契约 SDK、核心、平台资源层、通用宿主和 31 个独立插件包组成。核心拥有身份、受众、协调、授权、生命周期和操作记录，插件提供可变业务能力。当前公开契约是装载标准，产物摘要、实例代次和配置修订各有独立语义。

## Technical Context

| 项目 | 设计结果 |
| --- | --- |
| 语言 | Python 3.11，TypeScript / React / Vite 控制台 |
| 契约 | typing、dataclasses、Pydantic 2、JSON Schema |
| 核心与宿主 | asyncio、importlib.metadata、CLI、FastAPI |
| 平台资源 | SQLAlchemy async、asyncpg、Alembic、NATS、Redis、APScheduler、OpenTelemetry |
| 规划时配置适配 | Nacos 默认输入与控制库 override |
| 当前部署配置 | Kubernetes 挂载卷，见 docs/kubernetes-config.md |
| 持久控制数据 | PostgreSQL 实例、绑定、操作及发送账本 |
| 记忆活动 | JetStream、KV 水位和 CAS claim |
| 产物 | 独立 wheel、清单、schema、依赖锁及摘要 |
| 验收 | 正式宿主、公开 API、平台边界替身、本地持久设施、浏览器 |

## Project Structure

```text
packages/
├── contracts/src/ailove_contracts/
├── core/src/ailove_core/
└── platform-runtime/src/ailove_platform/
hosts/runtime/src/ailove_host/
plugins/<plugin-slug>/
deployment/manifests/
deployment/local/
tests/plugin_contracts/
tests/plugin_integration/
tests/plugin_recovery/
tests/plugin_architecture/
```

## 31 包目标目录

| 插件包 | 职责 | 宿主与模式 |
| --- | --- | --- |
| channel-qq | QQ、联系人、白名单和 QZone 协议 | gateway worker |
| content-quote、content-forward、content-voice、content-image、content-file、content-at、content-text | 七种内容规范化 | gateway trusted-inprocess |
| conversation-langchain | 对话生成编排 | ai-agent worker |
| model-openai、model-anthropic、model-deepseek | 模型供应商协议 | 消费宿主的 worker |
| media-vision | 图片资源与视觉解释 | ai-agent worker |
| speech-gptsovits-client | 语音调用契约 | ai-agent worker |
| speech-gptsovits-engine、speech-mimo-engine | 合成引擎 | gptsovits worker |
| memory-default、relationship-default、sticker-default | 记忆、关系和表情 | ai-agent trusted-inprocess |
| social-proactive、social-group-participation、social-group-repeat、social-qzone | 四种社交决策 | ai-agent trusted-inprocess |
| tool-grounding、tool-weather、tool-music、tool-web-search | 业务工具 | extension-host worker |
| tool-mcp-bridge | 远端 MCP 客户端 | extension-host worker |
| live-director-default、live-avatar-default、live-stream-default | 场次与输出事件 | director / live-edge trusted-inprocess |

## 数据与控制结果

操作、活动绑定与代次位于同一 PostgreSQL 提交边界，scope 及实例目录具有明确拥有者。资源由 ResourceScope 登记，可撤销能力租约与动作端口决定当前执行资格。

Memory 的交接资料包含数据库、KV 和 consumer 共同静止水位；持久活动、来源、person/self 边界及批量归并语义保留。私聊账本保留 run_id、固定摘要、claim_version 及 unknown。

通用 worker 使用带长度 JSON 的双向 stdio，可信进程内插件采用声明的代码生效方式。UI 使用 status/form/table/document 等受限贡献及固定通用路由。

## Constitution Check

目标结果包含持续身份、来源记忆、独立人物与受众范围、动作确认、清晰边界及真实入口证据。Memory 保持同进程，既有持久数据和迁移历史保留，外部写入对应明确授权。

## 验收目标

2 AI、20 会话、每秒 10 事件、900 秒；P95 增量 ≤max(基线×10%,20ms)，调用和 token 量至多为基线。控制阶段 30 秒，排空 60 秒，联合恢复 ≤5 分钟，每插件 100 次启停资源回到基线。

2026-09-16 的规划结构核验结果为 112 个连续任务、30 个 [P] 标签、31 包映射及 25 个 FR 覆盖，schema 与架构示例校验通过。业务验收证据按 [acceptance.md](acceptance.md) 的目标标准归档。
