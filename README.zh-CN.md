# Luoyu

[English](README.md)

Luoyu 是一个运行在你自己的 QQ 账号上的个性化机器人。你可以设置它的人设、记忆和
回复规则。Luoyu 是
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的插件。

一个 QQ 聊天对应一个 Harness 会话。群聊保留自己的历史，私聊也保留自己的历史。
长期记忆是你指定目录中的一组 Markdown 文件。Agent 用自己的文件工具读写这些文件。
插件不使用数据库。

## 工作原理

~~~mermaid
flowchart LR
    QQ[QQ 账号] --> NapCat
    NapCat -->|OneBot 11| Plugin[插件]
    Plugin --> Session[每个聊天一个 Harness 会话]
    Session --> Memory[工作区中的 Markdown 记忆]
    Session --> Plugin
    Plugin -->|OneBot 11| NapCat
    NapCat --> QQ
~~~

插件启动 NapCat。NapCat 加载官方 QQ 客户端，并使用 OneBot 11 协议。插件通过
WebSocket 接收事件，通过 HTTP 发送动作。

插件把一条 QQ 消息转换为一个会话回合。它从会话日志中读取回答，然后把回答发回
聊天。

| 模块 | 作用 |
| --- | --- |
| `src/napcat.ts` | 下载、配置并启动 NapCat，读取登录状态。 |
| `src/onebot/` | OneBot 11 客户端、消息段和纯文本渲染。 |
| `src/bridge.ts` | 把一个聊天映射到一个会话，把一个回合转换为一条回复。 |
| `src/workspace.ts` | 创建人设文件、指令文件和记忆文件。 |
| `src/state.ts` | 保存聊天到会话的映射，以及已处理消息的标识。 |
| `src/web.ts` | 提供状态页和登录二维码。 |

## 安装

在 Harness 配置中安装插件：

~~~bash
dsh plugin --profile web add dsh-luoyu
~~~

启动 Harness。打开 **设置 → Luoyu**，设置工作区和人设。你也可以在这里管理
NapCat。

Luoyu 区域显示登录状态。点击 **启动 NapCat**。插件会下载并启动 NapCat。用手机
QQ 扫描二维码。登录完成后，插件连接 NapCat。

状态页位于 `http://127.0.0.1:3080/luoyu`。设置区域会把每次更改保存到当前配置。
如果你更改工作区，每个 QQ 聊天都会启动新的 DSH 会话。现有会话仍保留在 DSH 中。

## 环境要求

- DeepSeek Harness 0.2.x。
- Node.js 22.19 或更高版本。
- 官方 Linux QQ 客户端：<https://im.qq.com/linuxqq/>。
- 显示服务器。QQ 客户端是 Electron 应用。如果主机没有桌面，请安装 Xvfb，并用
  `xvfb-run` 启动 Harness。

状态页会报告缺失的依赖。它不会隐藏错误。

## 配置

每个字段都有默认值。通常需要修改的是 QQ 号和工作区：

| 键 | 默认值 | 含义 |
| --- | --- | --- |
| `workspaceDir` | `/workspace/memroy` | 保存人设、记忆文件和所有会话。 |
| `persona` | 一段简短的机器人人设 | 写入 `PERSONA.md`。可在 **设置 → Luoyu** 中编辑。 |
| `privateReply` | `true` | 回复私聊消息。 |
| `groupReply` | `balanced` | 立即回复直接提及。适度模式下，在三分钟内有两条消息的活跃群聊中参与，两条回复之间等待 90 到 300 秒。 |
| `uin` | 空 | 账号的 QQ 号。托管模式在为空时读取登录状态。 |
| `napcatMode` | `managed` | 让插件运行 NapCat，或连接你自己运行的 NapCat。 |
| `wsUrl` | `ws://127.0.0.1:3001` | OneBot 事件流。 |
| `httpUrl` | `http://127.0.0.1:3000` | OneBot 动作接口。 |
| `accessToken` | 空 | NapCat 要求的令牌。 |
| `napcatDir` | `<DSH_HOME>/integrations/dsh-luoyu/napcat` | 托管模式下的 NapCat 安装目录。 |
| `napcatVersion` | `latest` | NapCat 发布标签。 |
| `napcatWebuiPort` | `6099` | NapCat Web 界面的端口。 |
| `napcatWebuiToken` | 空 | NapCat Web 界面的令牌。 |
| `autoStart` | `true` | 插件启动时启动托管模式下的 NapCat。 |
| `permissionPreset` | `danger-full-access` | 每个聊天会话的权限预设。 |
| `timeZone` | `Asia/Shanghai` | 插件在每个提示词中报告的时区。 |
| `maxReplyChars` | `1500` | 回复的最大字符数。更长的回复会被拆分。 |
| `turnTimeoutMs` | `600000` | 一个回合的时间限制，单位毫秒。 |

聊天会话请使用 `danger-full-access`。等待审批的会话永远不会回复 QQ 消息，因为
终端前没有人批准请求。

## 工作区

插件在首次启动时创建这些文件。它不会覆盖你编辑过的文件。

~~~
AGENTS.md                  Harness 为每个会话加载的指令
PERSONA.md                 机器人是谁
memory/self.md             机器人对自己的了解
memory/people.md           每个人一个段落
memory/episodes.md         以后会用到的带日期事件
memory/open-threads.md     尚未结束的问题和承诺
~~~

Harness 从会话的工作目录加载 `AGENTS.md`。每个聊天会话都把 `workspaceDir` 作为
工作目录。因此，每个会话读取相同的指令和相同的记忆。

Agent 用自己的文件工具搜索记忆。它不会把所有文件都加载到提示词中。这样可以让
长期记忆保持低成本，也让 Agent 选择重要的内容。

## 状态

插件在 `<DSH_HOME>/integrations/dsh-luoyu/state.json` 保存一个状态文件。它包含
聊天到会话的映射，以及最近 2000 条已处理消息的标识。文件权限为 `0600`。

如果状态文件损坏，插件会把它重命名为 `state.json.corrupt`，然后以空状态启动。
会话仍保留在磁盘上。新的映射会创建新的会话。

## 安全

- OneBot 服务只监听 `127.0.0.1`。
- 插件以 `0600` 权限写入状态文件。
- 插件不会把令牌写入日志。
- 人设禁止泄露凭据。
- 记忆文件包含个人数据。请把工作区放在你控制的主机上。

## 开发

~~~bash
npm install
npm run typecheck
npm test
npm run build
~~~

测试使用 Node.js 测试运行器和 Node 22 的原生 TypeScript 支持。测试不需要构建，
也不会启动 NapCat。

`npm run build` 生成 `lib/index.js`。Harness 加载这个文件。因此，修改源码后必须
重新构建，Harness 才能读到新代码。

## 限制

- 插件只支持 OneBot 11 协议，不支持官方 QQ 机器人 API。
- 插件只发送文本，不发送图片、语音或表情。
- 适度模式会在三分钟内有两条消息的活跃群聊中参与。两条回复之间等待 90 到 300 秒。
  它不会主动发送消息。
- 托管模式需要 Linux QQ 客户端和显示服务器。
- 一个会话只对应一个聊天。活跃聊天的上下文会比安静聊天更早达到上限。
