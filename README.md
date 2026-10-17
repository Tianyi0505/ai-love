# AI-Love

AI-Love runs persistent digital AI identities on social and live platforms. Each identity has a persona, memory, relationship state, account ownership, and approved tools.

## Runtime

| Unit | Current responsibility |
| --- | --- |
| gateway | Receives platform events, resolves account ownership, and delivers social messages. |
| ai-agent | Runs personas, conversation turns, memory, and social behavior. |
| gptsovits | Produces speech through HTTP and NATS. |
| extension-host | Lists approved tools and runs approved tool calls. |
| mcp | Serves structured output, weather, music-control, and web-search tools. |
| director | Routes live events to active AI actors. |
| live-edge | Routes avatar and stream commands to configured adapters. |

The gateway sends normalized social events to the assigned AI. The AI creates a typed response plan. The gateway delivers the selected text, voice, or sticker action.

~~~mermaid
flowchart LR
    Platform --> Gateway
    Gateway --> Agent
    Agent --> Memory
    Agent --> Tools
    Tools --> MCP
    Agent --> Speech
    Speech --> Gateway
    Gateway --> Platform
~~~

## Source layout

~~~
agent/              AI runtime, conversation, social, vision, and speech clients
gateway/            Platform channels, routing, delivery, and QZone support
gptsovits/          Speech service and speech-engine adapters
memory/             Memory extraction, storage, retrieval, and consolidation
extensions/         Tool host and MCP tools
live/               Director, avatar, stream, and live-edge modules
plugin_runtime/     Plugin catalog, lifecycle, resources, and management
shared/             Contracts, database models, settings, and infrastructure
admin/console/      Operations API and web interface
deploy/             Container, Kubernetes, and mounted configuration assets
~~~

## Configuration

The active deployment mounts configuration and secrets. The source templates are in deploy/config.

| Configuration key | Content |
| --- | --- |
| agent.catalog | Active AI identifiers. |
| agent.default | Shared persona rules, tools, models, and prompt templates. |
| agent.<ai_id> | Identity, voice, avatar, and persona overrides. |
| service.<name> | A service address and service-specific settings. |
| director.<session_id> | Live actors and live timing. |
| ailove.config | Global models, social, memory, image, and timeout settings. |

The agent definition merges the shared default with the AI override. Account bindings in PostgreSQL define trusted account ownership.

## Data and model results

PostgreSQL stores identities, conversations, memory, plugin state, and operations. NATS carries typed service events and RPC requests. JetStream and KV state support durable memory activity and ownership claims.

The model profile selects the primary text model and the optional multimodal model group. The image service creates image descriptions. The speech service creates playable audio. The response pipeline uses typed output tools for replies, participation, image decisions, and memory.

See docs/database-schema.md, docs/prompt-output.md, docs/plugin-runtime.md, and docs/agentscope-runtime.md.

## Local start

Start the local stack with:

~~~bash
docker compose -f deploy/docker-compose.yml up -d
~~~

Use Python 3.11, PostgreSQL with pgvector, NATS, Docker Compose, and the configured platform services.
