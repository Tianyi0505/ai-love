# 彻底移除礼物/打赏功能

> 创建时间：2026-08-26
> 影响范围：直播事件入口、关系策略、Nacos 关系配置
> 决策：拒绝将 AI 人际关系与金钱挂钩，礼物事件在网关入口即拒收，相关代码与配置全部删除

## 一、决策

亲密度只由聊天互动决定，不接受金钱维度输入。

- 亲密度 = 聊天互动（消息频率、内容质量、回复及时性）
- 亲密度 ≠ 礼物金额
- 礼物事件不是「收下但不加分」，而是**网关入口直接丢弃，不进入总线**

## 二、删除清单（已核对代码）

| 文件 | 删除内容 | 位置 |
|------|---------|------|
| `shared/contracts/relationship.py` | `on_gift()` 方法及其上方注释 | 184-211 |
| `shared/contracts/live.py` | `InteractionType.GIFT` 枚举成员 | 14 |
| `shared/contracts/relationship_policy_config.py` | `GiftRelationshipConfig` 类 | 23-27 |
| `shared/contracts/relationship_policy_config.py` | `RelationshipPolicyConfig.gift` 字段 | 71 |
| `shared/contracts/relationship_policy_config.py` | `RelationshipBounds.gift_amount_min` 字段 | 14 |
| `deploy/nacos/agent.default.yaml` | `relationship_policy.gift` 配置段 | 25-29 |
| `deploy/nacos/agent.default.yaml` | `relationship_policy.bounds.gift_amount_min` | 20 |

真实枚举是 `InteractionType`（成员 `DANMAKU`/`GIFT`/`GUARD`/`ENTER`/`FOLLOW`/`SUPER_CHAT`/`RAFFLE`/`LIVE_START`/`LIVE_END`），只删 `GIFT` 一个成员，枚举本身保留。

关系策略入口实际是 `on_conversation`/`on_gift`/`on_trust_event`/`on_group_conversation`，删除后保留前述三个。

## 三、网关入口拒收

`gateway/gateway_message_handler.py:75` 原先直接 `InteractionType(message.meta["bili_type"])`。删掉 `GIFT` 后，若上游送来 `bili_type="gift"`，这里会抛 `ValueError` 把整个 handler 打断——这不是「不接收」，是崩。

改为白名单解析：只有能落到 `InteractionType` 的事件才构造 `InteractionEvent` 并发布，其余（含 gift 及任何未知类型）直接丢弃返回。`meta` 缺 `bili_type` 时也走同一条丢弃路径，不再抛 `KeyError`。

这样礼物在进入 NATS 之前就被拦掉，agent 侧完全不可见，且代码里不需要出现 "gift" 字样。

## 四、实施约束

**配置与模型必须同一提交落地。** `RelationshipConfigModel` 是 `extra="forbid"` + `frozen=True`，双向严格：

- 只删 YAML 不删模型字段 → 缺必填字段，校验失败
- 只删模型字段不删 YAML → 出现未声明 key，校验失败

两边分开提交会让中间态无法启动。

## 五、遗留设计缺口

`on_gift` 是全仓唯一对 `lfu_state["importance"]` 执行 `access()` 的地方。删除后 `importance` 只衰减、无增长来源，会长期趋零。

本次不处理：`importance` 字段本身在 `shared/relationship_repository.py`、`gateway/qzone_context_provider.py`、`memory/relationship_handler.py` 仍在读写，属于有效关系维度。后续需要单独决定由哪个聊天维度接管其增长，或整体清理该字段。

`ailove.config.yaml` 的 `live.default_importance` 与 `memory` 的 `importance` 是不同概念（直播事件权重、记忆原子权重），与本次删除无关，保留。

## 六、验证

```bash
# 1. 全仓无残留
grep -ri gift . --exclude-dir=.git

# 2. 关系策略 + 配置校验（该测试直接加载 deploy/nacos/agent.default.yaml，
#    是 YAML 与模型漂移的守门测试）
pytest tests/test_lfu.py -v
```

数据库：`person_relationships` 表结构不变，无历史礼物数据，无需迁移。

部署：ai-agent / gateway 需重新构建导入镜像，Nacos `agent.default.yaml` 需同步更新（流程见 `docs/deploy-workflow.md`）。
