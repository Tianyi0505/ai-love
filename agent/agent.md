# AI Agent Runtime

ai-agent hosts multiple AIRuntime instances and one shared MemoryModule. Start the service with python -m agent.ai_agent_service.

## Runtime results

- Each runtime serves one stable ai_id.
- The gateway and director provide trusted event ownership.
- The definition store merges agent.default and agent.<ai_id>.
- The supervisor refreshes the runtime catalog and preserves matching runtime state.
- Each runtime provides persona, prompts, chat generation, vision, memory, stickers, speech, tools, and social behavior.
- The turn coordinator orders work for one conversation and supports parallel conversations.
- Social replies use social.send.request.
- Memory activity uses memory.activity.

## Memory results

The memory module shares the agent host configuration, bus, scheduler, definition store, and database. NATS RPC exposes memory, relationship, and sticker contracts. JetStream records durable activity. PostgreSQL stores episodes, atoms, sources, and long-term documents.

## Configuration

service.ai-agent defines the service instance and polling intervals. agent.default defines shared behavior. agent.<ai_id> defines identity overrides. ailove.config defines models, memory, social settings, timeouts, and observability.
