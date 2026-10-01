# 以聊天互动为依据的人物关系

**设计日期**：2026-08-26。本文定义关系与直播事件的目标结果。

亲密度依据消息频率、内容质量和回复及时性。关系策略的有效入口为 `on_conversation`、`on_trust_event` 和 `on_group_conversation`。

## 事件与配置结果

网关发布的 `InteractionEvent` 属于 `InteractionType` 声明的允许事件集合。平台消息具有合法 `bili_type` 时，事件解析与总线发布结果明确；其余输入以结束处理的状态返回。

`InteractionType` 的目标成员为 DANMAKU、GUARD、ENTER、FOLLOW、SUPER_CHAT、RAFFLE、LIVE_START、LIVE_END。关系配置的字段集合与 `RelationshipConfigModel` 一致，模型采用 `extra="forbid"`、`frozen=True`。配置与模型处于同一交付版本。

## 数据归属

`person_relationships` 的关系维度和持久数据保留。`importance` 的现有读写归属为关系仓库、QQ 空间上下文与关系处理器；增长策略属于单独的关系设计。`live.default_importance` 表达直播事件权重，Memory 的 `importance` 表达记忆原子权重，各自保持独立含义。

## 验收标准

- 亲密度变化有聊天互动依据。
- 发布事件属于合法枚举集合。
- 关系配置通过模型校验。
- 人物关系表及既有数据完整保留。

配置契约验收入口：

```bash
pytest tests/test_lfu.py -v
```
