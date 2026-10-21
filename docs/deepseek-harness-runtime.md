# DeepSeek Harness runtime

## Runtime ownership

DeepSeek Harness is the only Agent runtime and operations plane. It owns model access, Agent loops, session logs, tools, process lifecycle, logs, configuration and the Web operator interface. AI-Love is one optional social-conversation plugin; it does not recreate those capabilities.

There are no technical-layer business plugins such as gateway, memory, model or speech plugins. Related behavior stays inside the single `ai-love` feature boundary, so the business-plugin dependency graph has one node and zero edges.

## Conversation to session mapping

Every incoming group or private chat maps to one deterministic DSH session. The session key is the SHA-256 digest of these values, separated unambiguously:

1. `platform`
2. `accountId`
3. `chatType` (`group` or `private`)
4. `chatId`

Changing any field creates a different session. Reusing all four fields resumes the same session, including after the plugin process restarts when the selected DSH profile has session persistence enabled.

Messages within one session are serialized. Different chats can be processed independently.

## Project and Markdown memory

Set `AILOVE_WORKSPACE_DIRECTORY` to the absolute directory that the Agent should operate in. The DSH process starts in that directory and each chat Agent receives it as `cwd`, so the DSH workspace sandbox and Agent tools share the same boundary. AI-Love creates only the following memory structure inside it:

```text
<workspace>/
└── .ai-love/
    └── memory/
        ├── shared/
        │   └── README.md
        ├── identities/
        │   └── <identity>/
        │       └── MEMORY.md
        └── conversations/
            └── <dsh-session-id>/
                └── MEMORY.md
```

Before answering, the Agent is instructed to read relevant Markdown itself with DSH file tools. It may update Markdown for durable facts. No memory database, vector service, retrieval API or NATS request is involved.

- `shared`: facts allowed to cross every chat and identity.
- `identities/<identity>`: facts shared by one digital identity across its chats.
- `conversations/<session>`: facts private to one group or private chat.

`AILOVE_MEMORY_DIRECTORY` may change the relative memory path, but it must resolve inside the workspace. This prevents a plugin setting from redirecting memory outside the selected project.

## Message ingress

The TypeScript HTTP adapter exposes:

- `GET /healthz`
- `POST /v1/chat`
- `POST /v1/messages` (alias)

Canonical request:

```json
{
  "platform": "qq",
  "accountId": "bot-1",
  "chatType": "group",
  "chatId": "group-10001",
  "senderId": "user-20002",
  "senderName": "Alice",
  "messageId": "message-30003",
  "aiId": "luoyu",
  "text": "晚上好"
}
```

Response:

```json
{
  "sessionId": "ai-love-<digest>",
  "text": "Agent reply",
  "memoryDirectory": "<workspace>/.ai-love/memory/conversations/ai-love-<digest>"
}
```

The adapter also accepts the former nested `chat`, `sender` and `meta` message shape to ease channel migration; this is input compatibility only, not a legacy runtime.

The default listener is `127.0.0.1:8090`. A bearer token is mandatory when binding to a non-loopback address. The request body limit is 1 MiB.

## Plugin removal semantics

The Cordis bundle inserts exactly one row and declares no top-level `inject` or `requires` metadata. Its use of DSH's `agents` service is optional activation: without that service, the plugin only initializes the safe Markdown directory and does not prevent the host from booting. Removing or disabling AI-Love cannot remove DSH core Agent, session, model, tools or plugin-management functionality.
