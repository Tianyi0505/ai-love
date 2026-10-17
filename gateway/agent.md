# Gateway Runtime

Start the gateway with python -m gateway.gateway_service. The gateway receives platform events, assigns trusted account ownership, and delivers platform messages.

## Message results

- Each inbound SocialMessage contains sender, account, conversation, and entity context.
- Social messages use social.chat.{ai_id}. Live events use live.events.
- SocialSendHandler delivers social.send.request through the source account and conversation.
- identity.resolve-people.request, history.search-group.request, and social.send.request use shared contract models.
- Images and voice travel as URLs.
- Channel adapters load through the ai_love.channels entry-point group.

## Platform support

QQChannel provides NapCat WebSocket and HTTP access, quoted replies, forwarded messages, content handling, and delivery. QZone actions use the bound AI identity, the behavior schedule, and relationship state.

service.gateway defines service, account, adapter, and platform settings. ailove.config defines platform limits, retention, entity grounding, relationship, and QZone values.
