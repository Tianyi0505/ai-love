# AI-Love for DeepSeek Harness

AI-Love 现在是一个可直接导入 DeepSeek Harness（DSH）的 TypeScript 插件。DSH 负责 Agent、模型、会话、工具和运维；本仓库只提供社交会话入口、聊天到 DSH 会话的映射，以及项目目录内的 Markdown 长期记忆。

## 架构边界

- 仓库只导出一个业务插件 `ai-love`，没有业务插件之间的依赖关系。
- QQ、群聊平台或其他通道只需把标准消息提交到 HTTP 入口。
- 每个群聊或私聊由 `platform + accountId + chatType + chatId` 稳定映射成一个 DSH 会话。
- Agent 的工作目录就是指定的项目目录；它直接使用 DSH 文件工具读取和维护 Markdown，不再经过独立记忆查询服务。
- 删除 `ai-love` 插件只会移除这项业务功能，不影响 DSH 自身的 Agent、会话、模型和插件管理能力。

```text
聊天平台 -> AI-Love HTTP 入口 -> DSH Agent/Session
                                      |
                                      +-> <项目目录>/.ai-love/memory/**/*.md
```

## 直接导入

在已安装 DSH 的环境中运行：

```powershell
dsh plugin --profile web add D:\ai-love
```

仓库根目录的 `package.json` 和 `harness/bundle/cordis.patch.yml` 是 DSH 的导入入口。

## 本地运行

需要 Node.js 22、pnpm 11 和 `DEEPSEEK_API_KEY`：

```powershell
Set-Location D:\ai-love\harness
pnpm install --frozen-lockfile
$env:DEEPSEEK_API_KEY = 'your-key'
$env:AILOVE_WORKSPACE_DIRECTORY = 'D:\your-agent-workspace'
pnpm start -- --no-open --port 3080
```

DSH 本身也从该工作目录启动，因此 DSH 的工作区沙箱与 Agent `cwd` 指向同一个指定目录。

默认地址：

- DSH Web：`http://127.0.0.1:3080`
- 消息入口：`http://127.0.0.1:8090/v1/chat`
- 健康检查：`http://127.0.0.1:8090/healthz`

请求示例：

```powershell
$body = @{
  platform = 'qq'
  accountId = 'bot-1'
  chatType = 'group'
  chatId = 'group-10001'
  senderId = 'user-20002'
  senderName = 'Alice'
  aiId = 'luoyu'
  text = '晚上好'
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8090/v1/chat `
  -ContentType application/json `
  -Body $body
```

若 `AILOVE_INGRESS_HOST` 不是回环地址，必须设置 `AILOVE_INGRESS_TOKEN`，并由调用方发送 `Authorization: Bearer <token>`。

## Docker

复制 `deploy/.env.example` 为 `deploy/.env`，填写 API Key、入口 Token 和宿主机工作目录，然后运行：

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.harness.yml up --build
```

更完整的会话、记忆和接口说明见 `docs/deepseek-harness-runtime.md`。
