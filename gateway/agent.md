# Gateway 运行边界


现有入口为 `python -m gateway.gateway_service`，统一插件入口见 [插件运行时](../docs/plugin-runtime.md)。Gateway 提供平台接入、消息归一化、可信账号归属与投递；Agent 提供内容理解和回复决策。

## 消息结果

- 入站 SocialMessage 具有发送者、账号、会话、实体 grounding 和数据库账号归属，社交主题为 social.chat.{ai_id}，直播主题为 live.events。
- 出站 social.send.request 由 SocialSendHandler 关联原平台账号及会话记录。
- identity.resolve-people.request、history.search-group.request 和 social.send.request 构成公开 RPC 边界，生产者与消费者使用 shared/contracts 模型。
- 图片与语音的传输形态为 URL。
- Channel 实现通过 ai_love.channels entry point 提供平台协议，平台选择由工厂配置确定。

## QQ 与 QQ 空间

QQChannel 提供 NapCat WebSocket/HTTP、引用、合并转发、内容策略和发送能力。超时来自全局配置。白名单采用既有配置；QQ 空间互动由账号绑定的 AI、行为日程和对应人物关系决定。

service.gateway 包含实例、账号、adapter 和平台连接；ailove.config 包含白名单、超时、保留期、grounding、关系及 QQ 空间参数。可信 AI 归属以 PostgreSQL 绑定为准。
