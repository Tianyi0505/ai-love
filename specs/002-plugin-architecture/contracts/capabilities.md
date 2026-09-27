# 当前能力契约和迁移映射

所有输入输出为 Pydantic/JSON 值对象；不携带 ORM、模型 SDK、异常或任意 host 引用。无 API 版本字段或 `@1` 命名。调用共有 scope/deadline/cancel/授权/幂等语义见 [lifecycle.md](lifecycle.md)。详细字段首先复用现有 shared/contracts 中事实性 DTO，转换为独立 ailove_contracts 后移除实现依赖。

| 能力与方法 | 输入 → 输出 | 行为约束 / 现有映射 |
|---|---|---|
| channel.receive / send / hydrate / contacts / members / capabilities | 平台事件→SocialMessage；ResponseCommand→DeliveryReceipt；联系人/群标识→结构化事实 | 保留发送者、引用、账号和平台 ID；无语义决策。Channel/QQChannel，发送账本在核心 |
| channel.feed.list / like / comment | 账号/分页→FeedFacts；固定 feed_id+动作意图→ActionReceipt | QZone 协议由渠道提供，关系与评论生成归 social.policy；like/comment 必须有核心动作许可和幂等记录 |
| content.normalize.apply | ContentContext→`{matched, content}` | quote/forward/voice/image/file/at/text 显式顺序；未命中继续下一策略，无外部动作 |
| conversation.generate.plan | TurnInput（persona/context/messages/tools/budget）→ResponsePlan 或流 | 工具调用意图经核心 ActionPort；禁止让 LangChain ToolRuntime 自报身份扩大权限 |
| model.generate.complete / stream | 标准 text/image/tool-result 片段+工具 schema+budget→输出片段、工具意图、usage | 显式顺序故障切换；各适配器不能导出 BaseChatModel；流结束必须有结果或错误 |
| media.describe | 有来源/受众的 ResourceRef→description/evidence/unsupported | 非支持输入不得伪造理解；由网络代理限制抓取范围和大小 |
| speech.synthesize | ai_id、text、voice_ref→AudioReference（resource_id/media_type/duration） | 复用 TTSProvider/SpeechEngine；客户端/引擎各自独立，音频不进入大 IPC 帧 |
| memory.query / search / activity / transfer | owner+query→文档/来源；持久 activity→receipt；静止点→状态引用 | owner 为 AI/person/self；activity 持久接收后确认；批处理/静默窗口保留 |
| relationship.query / observe / list | ai/person+事实→关系视图 | 只更新对应人关系，核心 Scope 约束归属；复用 relationship RPC |
| sticker.search / add / boost | 素材事实/检索上下文→候选或回执 | 保留文件与归属，缺失可不发表情；不能以删除插件代替素材保留策略 |
| social.policy.decide | read-only context（触发类型、消息/关系/作息）→participate/silent/proactive/comment 意图 | 四个策略插件分别绑定；核心验证身份、受众、作息上限和动作授权 |
| tool.list / execute | scope→descriptor[]；工具名+arguments→ToolResult | descriptor 带 operation/side_effect；执行端依据可信授权再次核验；永久禁用不可被元数据绕开 |
| live.director.decide | 场次/参与者/事件→发言或输出意图 | 不改变人物身份；仅按场次绑定 |
| avatar.execute / stream.execute | 规范化舞台/推流命令→ActionReceipt | 当前实现是日志回调；未实现外部动作时显式 unsupported，不返回真实成功 |
| ui.contribution.describe / query / action | 贡献 ID 与参数→声明式视图或结果 | kind=status/form/table/document；固定查询/动作引用，不含 JS、可执行表达式或任意 URL |

## 核心和平台提供的端口

- IdentityPort：resolve/query、account ownership；可信事实来自入站渠道加核心账号绑定，而非模型猜测。
- ConversationPort/PrivateJobPort：持久入站、顺序、claim/heartbeat/prepare/complete；实现保留既有领取条件。
- ActionPort：authorize/prepare/execute/status；运行幂等键和内容摘要不可在重试中变化。群聊/QZone/直播不能绕过此端口。
- MemoryStatePort：按 owner 访问 Episode/Atom/文档、水位和 pending 集；不把数据库连接暴露给插件。
- EventPort：publish/subscribe/request/reply，资源句柄受 Scope 管理；只提供获准 subject 和有限队列，持久确认语义明确。
- ScopedStore：namespace/owner/key 范围读写/事务请求；私有 migration 由管理操作执行，不接受运行时任意 SQL。
- ConfigPort：读取已验证快照/订阅修订；插件不能调用 Nacos 管理写接口。
- SessionPort、ResourcePort、SchedulerPort、TelemetryPort：固定操作集合，限制 TTL、范围、资源和日志内容。

这些基础设施端口不作为业务插件版本系统的一部分，也不得通过 `get_service(name)` 返回任意核心对象。

## 执行动作的结果

DeliveryReceipt 延续 sent/rejected/retryable-not-sent/unknown/reply-unavailable。`retryable-not-sent` 必须有确定未发送依据；取消发送和网络超时不自动满足。引用不可用时沿用仅一次去引用修改的规则。对实际尚未实现的平台动作返回 unsupported，不将记录日志当作平台确认。

## 验证映射

每个插件必须在 contracts/plugin.schema.json 校验、对应能力测试、正式宿主业务链和六种管理变更中验证。SDK 的测试插件覆盖失败机制，不能替代 31 个实际包。能力绑定按显式配置/唯一候选确定，不依据包名分支或扫描顺序。
