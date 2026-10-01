# 当前能力契约与目标归属

输入输出采用 Pydantic/JSON 值对象，契约边界包含 scope、deadline、cancel、授权与幂等语义。现有 shared/contracts 事实 DTO 对应目标 ailove_contracts。

| 能力 | 输入与结果 | 归属 |
| --- | --- | --- |
| channel.receive/send/hydrate/contacts/members/capabilities | 平台事实、SocialMessage、ResponseCommand 与 DeliveryReceipt | 平台协议，发送账本归核心 |
| channel.feed.list/like/comment | 分页 FeedFacts 与 ActionReceipt | QZone 协议，关系意图归社交能力 |
| content.normalize.apply | ContentContext 与 matched/content | 有序内容规范化 |
| conversation.generate.plan | TurnInput 与 ResponsePlan | 人物上下文、工具意图和预算 |
| model.generate.complete/stream | 标准消息、工具 schema 与输出、usage | 供应商适配 |
| media.describe | 有来源 ResourceRef 与描述、evidence、状态 | 媒体理解 |
| speech.synthesize | ai_id、text、voice_ref 与 AudioReference | 语音客户端与引擎 |
| memory.query/search/activity/transfer | owner、活动、水位与文档、receipt、快照 | 静默 Episode 与批量文档 |
| relationship.query/observe/list | ai/person 事实与关系视图 | 独立人物关系 |
| sticker.search/add/boost | 素材与候选、回执 | AI 素材归属 |
| social.policy.decide | 只读场景与参与、旁听、主动、评论意图 | 社交决策 |
| tool.list/execute | 可信 scope、arguments 与 descriptor、ToolResult | 工具目录和原子业务 |
| live.director.decide | 场次、参与者、事件与调度意图 | 场次范围 |
| avatar.execute/stream.execute | 舞台命令与 ActionReceipt | 当前事件回调与实际驱动回执 |
| ui.contribution.describe/query/action | 贡献引用与声明式数据 | status/form/table/document |

## 核心及平台端口

IdentityPort 提供可信实体和账号归属。ConversationPort / PrivateJobPort 提供入站、顺序、有效领取及任务结果。ActionPort 提供授权、固定意图、执行与状态。MemoryStatePort 提供 owner 范围的 Episode、Atom、文档及水位。

EventPort 提供批准 subject 和有限队列，ScopedStore 提供 namespace/owner/key 范围，ConfigPort 提供有效快照，SessionPort、ResourcePort、SchedulerPort、TelemetryPort 提供各自受限资源。

DeliveryReceipt 的状态为 sent、rejected、retryable-not-sent、unknown、reply-unavailable。执行确认来自平台或实际驱动，当前日志能力具有自身准确结果。

## 验收归属

每个实际插件具有清单校验、能力场景、正式宿主入口及六种管理变更证据。SDK 验收插件提供机制证据，31 个业务包各自提供业务证据。绑定采用显式范围或唯一候选。
