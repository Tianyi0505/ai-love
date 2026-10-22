# AI-Love

AI-Love runs an AI companion on your own QQ account. It is a plugin for
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness).

One QQ chat is one Harness session. A group chat and a private chat each keep
their own history. The long-term memory is a set of Markdown files in a
directory that you choose. The agent reads and writes these files with its own
file tools. There is no database.

## How it works

~~~mermaid
flowchart LR
    QQ[QQ account] --> NapCat
    NapCat -->|OneBot 11| Plugin
    Plugin --> Session[Harness session per chat]
    Session --> Memory[Markdown memory in your workspace]
    Session --> Plugin
    Plugin -->|OneBot 11| NapCat
    NapCat --> QQ
~~~

The plugin starts NapCat. NapCat loads the official QQ client and speaks the
OneBot 11 protocol. The plugin receives the events on a WebSocket and sends the
actions over HTTP.

The plugin turns one QQ message into one session turn. It reads the answer of
the turn from the session log and sends the answer back to the chat.

| Part | Task |
| --- | --- |
| `src/napcat.ts` | Downloads, configures, and starts NapCat. Reads the login state. |
| `src/onebot/` | OneBot 11 client, message segments, and plain-text rendering. |
| `src/bridge.ts` | Maps one chat to one session and settles one turn into one reply. |
| `src/workspace.ts` | Creates the persona file, the instruction file, and the memory files. |
| `src/state.ts` | Keeps the chat-to-session map and the seen message identities. |
| `src/web.ts` | Serves the status page and the login QR code. |

## Install

Install the plugin into a Harness profile:

~~~bash
dsh plugin --profile web add dsh-ai-love
~~~

Then start the Harness. Open **Settings → AI Love** to configure the workspace
and persona, and to manage NapCat.

The AI Love section shows the login state. Press **Start NapCat** to download and
start NapCat. Scan the QR code with the QQ mobile app. The plugin connects to
NapCat after the login.

The status page is available at `http://127.0.0.1:3080/dsh-ai-love`. The Settings
section saves changes to the active profile. If you change the workspace, each
QQ chat starts a new DSH session. Existing sessions remain available in DSH.

## Requirements

- DeepSeek Harness 0.2.x.
- Node.js 22.19 or later.
- The official Linux QQ client, from <https://im.qq.com/linuxqq/>.
- A display server. The QQ client is an Electron application. On a host without
  a desktop, install Xvfb and start the Harness under `xvfb-run`.

The status page reports a missing dependency. It does not hide the failure.

## Configuration

Every field has a default. Set the account and the workspace:

| Key | Default | Meaning |
| --- | --- | --- |
| `workspaceDir` | `<DSH_HOME>/integrations/dsh-ai-love/workspace` | Holds the persona, the memory files, and every session. |
| `persona` | A short companion persona | Written into `PERSONA.md`. Edit it in **Settings → AI Love**. |
| `privateReply` | `true` | Answer private messages. |
| `groupReply` | `mention` | Answer only a message that mentions the account, or every group message. |
| `uin` | empty | QQ number of the account. Managed mode reads the login state when this is empty. |
| `napcatMode` | `managed` | Let the plugin run NapCat, or connect to a NapCat that you run yourself. |
| `wsUrl` | `ws://127.0.0.1:3001` | OneBot event stream. |
| `httpUrl` | `http://127.0.0.1:3000` | OneBot action endpoint. |
| `accessToken` | empty | Token that NapCat requires. |
| `napcatDir` | `<DSH_HOME>/integrations/dsh-ai-love/napcat` | The managed NapCat installation. |
| `napcatVersion` | `latest` | NapCat release tag. |
| `napcatWebuiPort` | `6099` | Port of the NapCat web interface. |
| `napcatWebuiToken` | empty | Token of the NapCat web interface. |
| `autoStart` | `true` | Start the managed NapCat when the plugin starts. |
| `permissionPreset` | `danger-full-access` | Permission preset for each chat session. |
| `timeZone` | `Asia/Shanghai` | Zone that the plugin reports with each prompt. |
| `maxReplyChars` | `1500` | Largest reply, in characters. A longer reply is split. |
| `turnTimeoutMs` | `600000` | Time limit for one turn, in milliseconds. |

Use `danger-full-access` for the chat sessions. A session that waits for an
approval prompt never answers a QQ message, because no person is at the
terminal.

## The workspace

The plugin creates these files on the first start. It never overwrites a file
that you edited.

~~~
AGENTS.md                  Instructions that the Harness loads for every session
PERSONA.md                 Who the companion is
memory/self.md             What the companion learned about itself
memory/people.md           One section for each person
memory/episodes.md         Dated events that matter later
memory/open-threads.md     Questions and promises that are not closed
~~~

The Harness loads `AGENTS.md` from the working directory of a session. Every
chat session uses `workspaceDir` as its working directory, so every session
reads the same instructions and the same memory.

The agent searches the memory with its own file tools. It does not load every
file into the prompt. This keeps a long memory cheap and lets the agent choose
what matters.

## State

The plugin keeps one state file at
`<DSH_HOME>/integrations/dsh-ai-love/state.json`. It holds the chat-to-session
map and the last 2000 seen message identities. The file has mode `0600`.

A corrupt state file is renamed to `state.json.corrupt` and the plugin starts
with an empty state. The sessions stay on disk, so a new map creates new
sessions.

## Security

- The OneBot servers listen on `127.0.0.1` only.
- The plugin writes the state file with mode `0600`.
- The plugin never writes a token into a log.
- The persona forbids the disclosure of a credential.
- The memory files hold personal data. Keep the workspace on a host that you
  control.

## Development

~~~bash
npm install
npm run typecheck
npm test
npm run build
~~~

The tests use the Node.js test runner and the native TypeScript support of
Node 22. They do not need a build step. They do not start NapCat.

`npm run build` writes `lib/index.js`. The Harness loads this file, so a source
change needs a build before the Harness reads it.

## Limitations

- The plugin supports the OneBot 11 protocol only. It does not support the
  official QQ bot API.
- The plugin sends text only. It does not send an image, a voice message, or a
  sticker.
- The plugin answers a group message that mentions the account, or every group
  message. It has no participation score and no proactive message.
- The managed mode needs the Linux QQ client and a display server.
- One session holds one chat. A very active chat reaches the context limit
  sooner than a quiet chat.
