# AI-Love DeepSeek Harness plugin

This repository root is an importable DeepSeek Harness bundle. It contributes exactly one cohesive business plugin, `ai-love`, and declares no business-plugin dependency surface.

The plugin maps each group or private chat to one stable DSH session. It runs the Agent with the configured project directory as its workspace and instructs the Agent to read and maintain Markdown memory under `.ai-love/memory`. There is no separate retrieval service or legacy worker topology.

Import the repository directly:

```powershell
dsh plugin --profile web add D:\ai-love
```

DeepSeek Harness owns Agent execution, session persistence, model access, tools, logs, lifecycle, and the operator UI. Removing this plugin removes only the AI-Love social-conversation feature; DSH core continues to start and operate.
