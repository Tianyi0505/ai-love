# Plugin Runtime

The plugin runtime loads catalog entries, resolves dependencies, scopes resources, and exposes management operations.

## Catalog

The current catalog contains 17 built-in plugins.

| Host | Plugins |
| --- | --- |
| ai-agent | agent environment, agent, memory, models, speech clients |
| gateway | channels, gateway |
| gptsovits | speech engines, speech server |
| extension-host | tools |
| mcp | MCP server, structured output, weather, music, web search |
| director | director |
| live-edge | avatar module, stream module |

Each manifest defines an identifier, host, entry point, provided capabilities, required capabilities, enabled state, and configuration.

## Lifecycle

The runtime initializes dependencies before dependents. A plugin receives a scoped resource owner. The owner tracks tasks, subscriptions, HTTP clients, and cleanup actions. A stop operation drains the scoped resources and releases the provided capabilities.

## Management

The console exposes catalog state, dependency checks, installation, enablement, restart, removal, and operation results. The runtime records catalog and binding state in SQLite.

## Tool access

The extension host builds the tool catalog from enabled providers and AI-specific grants. A tool call carries a trusted execution context. The provider receives the scoped call and returns a typed result.
