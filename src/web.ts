/**
 * Status page and control routes.
 *
 * The plugin exposes one small page on the Harness web server. The page shows
 * the login state, the QR code, and the chat sessions. It also starts and
 * stops the NapCat sidecar, so the operator never needs a terminal.
 *
 * @module dsh-luoyu/web
 */

import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import type { ConfigEditorService, ConfigEntryLike, PluginContext, PluginLogger, WebRequest, WebResponse, WebServerService } from './context.ts'
import type { Config } from './config.ts'
import { resolveConfig } from './config.ts'
import { normalizeGroupReplyMode } from './group-rate.ts'
import { PERSONA_FILE, personaBody, personaText } from './workspace.ts'
import { optionalService } from './context.ts'
import type { NapCatSidecar, SidecarStatus } from './napcat.ts'
import type { ChatBridge } from './bridge.ts'

/** Prefix of every route that the plugin owns. */
export const ROUTE_PREFIX = '/luoyu'

/** The facts that the page renders. */
export interface StatusSnapshot {
  sidecar: SidecarStatus
  bridge: {
    chats: number
    connected: boolean
    uin: string
  }
  workspace: string
  log: readonly string[]
}

/** Read the request body as text. */
async function readBody(request: WebRequest, limit = 65_536): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const chunks: string[] = []
    let size = 0
    let settled = false
    request.on('data', (chunk: unknown) => {
      if (settled) return
      const bytes = typeof chunk === 'string' ? Buffer.byteLength(chunk) : Buffer.byteLength(Buffer.from(chunk as Uint8Array))
      size += bytes
      if (size > limit) {
        settled = true
        chunks.length = 0
        reject(new Error('The request body is too large.'))
        return
      }
      chunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk as Uint8Array).toString('utf8'))
    })
    request.on('end', () => {
      if (settled) return
      settled = true
      resolve(chunks.join(''))
    })
    request.on('error', error => {
      if (settled) return
      settled = true
      reject(error)
    })
  })
}

/** Send one JSON response. */
function sendJson(response: WebResponse, status: number, body: unknown): void {
  response.statusCode = status
  response.setHeader('content-type', 'application/json; charset=utf-8')
  response.setHeader('cache-control', 'no-store')
  response.end(`${JSON.stringify(body)}\n`)
}

/** Send one HTML response. */
function sendHtml(response: WebResponse, status: number, body: string): void {
  response.statusCode = status
  response.setHeader('content-type', 'text/html; charset=utf-8')
  response.setHeader('cache-control', 'no-store')
  response.end(body)
}

/** The page body. It polls the state route and shows the QR code. */
const PAGE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luoyu · QQ</title>
<style>
  :root { color-scheme: dark light; --bg:#0f1115; --card:#171a21; --line:#2a2f3a; --text:#e6e9ef; --muted:#8b93a1; --ok:#3ecf8e; --warn:#f5a524; --bad:#f05d5d; }
  @media (prefers-color-scheme: light) { :root { --bg:#f6f7f9; --card:#fff; --line:#e2e5ea; --text:#15181d; --muted:#6b7280; } }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }
  main { max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }
  h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
  p.sub { color: var(--muted); margin: 0 0 24px; font-size: 13px; }
  section { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; margin-bottom: 16px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 0 0 12px; font-weight: 600; }
  .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .pill { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:3px 10px; font-size:12px; border:1px solid var(--line); }
  .dot { width:7px; height:7px; border-radius:50%; background: var(--muted); }
  .ok .dot { background: var(--ok); } .ok { color: var(--ok); border-color: color-mix(in srgb, var(--ok) 40%, var(--line)); }
  .warn .dot { background: var(--warn); } .warn { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 40%, var(--line)); }
  .bad .dot { background: var(--bad); } .bad { color: var(--bad); border-color: color-mix(in srgb, var(--bad) 40%, var(--line)); }
  button { font: inherit; font-size: 13px; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--line); background: transparent; color: var(--text); cursor: pointer; }
  button:hover { border-color: var(--muted); }
  button.primary { background: var(--text); color: var(--bg); border-color: var(--text); }
  button:disabled { opacity: .45; cursor: default; }
  dl { display: grid; grid-template-columns: 150px 1fr; gap: 8px 16px; margin: 0; font-size: 13px; }
  dt { color: var(--muted); } dd { margin: 0; word-break: break-all; font-variant-numeric: tabular-nums; }
  #qr { display:flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }
  #qr img { width: 220px; height: 220px; image-rendering: pixelated; border-radius: 10px; background:#fff; padding:8px; border:1px solid var(--line); }
  #qr .hint { flex: 1; min-width: 220px; color: var(--muted); font-size: 13px; }
  pre { margin: 0; font: 12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; white-space: pre-wrap; word-break: break-all; max-height: 260px; overflow: auto; color: var(--muted); }
  .hidden { display: none !important; }
</style>
</head>
<body>
<main>
  <h1>Luoyu · QQ</h1>
  <p class="sub">One DeepSeek Harness session per chat. Memory lives in the workspace as Markdown.</p>

  <section>
    <h2>Account</h2>
    <div class="row" style="margin-bottom:14px">
      <span id="phase" class="pill"><span class="dot"></span><span id="phaseText">…</span></span>
      <span id="bridge" class="pill"><span class="dot"></span><span id="bridgeText">…</span></span>
      <span style="flex:1"></span>
      <button id="start" class="primary">Start</button>
      <button id="stop">Stop</button>
      <button id="refresh">New QR code</button>
    </div>
    <dl>
      <dt>Detail</dt><dd id="detail">…</dd>
      <dt>QQ number</dt><dd id="uin">–</dd>
      <dt>Nickname</dt><dd id="nick">–</dd>
      <dt>NapCat</dt><dd id="napcat">–</dd>
      <dt>QQ client</dt><dd id="qq">–</dd>
      <dt>Workspace</dt><dd id="workspace">–</dd>
      <dt>Chats</dt><dd id="chats">–</dd>
    </dl>
  </section>

  <section id="qrSection" class="hidden">
    <h2>Login</h2>
    <div id="qr">
      <img id="qrimg" alt="QQ login QR code" src="">
      <div class="hint">
        Open QQ on your phone, tap the scan button, and confirm the login.
        The page updates by itself. The QR code expires after a few minutes;
        press <strong>New QR code</strong> if it stops working.
      </div>
    </div>
  </section>

  <section>
    <h2>Recent output</h2>
    <pre id="log">–</pre>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id)
let qrStamp = 0

function setPill(el, textEl, cls, text) {
  el.className = 'pill ' + cls
  textEl.textContent = text
}

async function poll() {
  try {
    const r = await fetch('${ROUTE_PREFIX}/state', { cache: 'no-store' })
    const s = await r.json()
    const phase = s.sidecar.phase
    const good = phase === 'online'
    const warn = phase === 'qrcode-ready' || phase === 'waiting-qrcode' || phase === 'scanned' || phase === 'starting'
    setPill($('phase'), $('phaseText'), good ? 'ok' : warn ? 'warn' : 'bad', phase)
    setPill($('bridge'), $('bridgeText'), s.bridge.connected ? 'ok' : 'bad', s.bridge.connected ? 'OneBot connected' : 'OneBot offline')
    $('detail').textContent = s.sidecar.detail
    $('uin').textContent = s.sidecar.uin || s.bridge.uin || '–'
    $('nick').textContent = s.sidecar.nickname || '–'
    $('napcat').textContent = s.sidecar.version ? s.sidecar.version + (s.sidecar.installed ? ' (installed)' : '') : 'not installed'
    $('qq').textContent = s.sidecar.qqPath || 'not found'
    $('workspace').textContent = s.workspace
    $('chats').textContent = String(s.bridge.chats)
    $('log').textContent = s.log.length ? s.log.join('\\n') : '–'
    $('start').disabled = s.sidecar.running
    $('stop').disabled = !s.sidecar.running
    if (s.sidecar.qrcodePath && phase !== 'online') {
      $('qrSection').classList.remove('hidden')
      const stamp = String(s.sidecar.updatedAt)
      if (stamp !== qrStamp) {
        qrStamp = stamp
        $('qrimg').src = '${ROUTE_PREFIX}/qrcode?t=' + encodeURIComponent(stamp)
      }
    } else if (phase === 'online') {
      $('qrSection').classList.add('hidden')
    }
  } catch (e) {
    setPill($('phase'), $('phaseText'), 'bad', 'unreachable')
  }
}

async function act(path) {
  try { await fetch('${ROUTE_PREFIX}/' + path, { method: 'POST' }) } catch (e) {}
  poll()
}

$('start').addEventListener('click', () => act('start'))
$('stop').addEventListener('click', () => act('stop'))
$('refresh').addEventListener('click', () => act('refresh-qrcode'))
poll()
setInterval(poll, 3000)
</script>
</body>
</html>
`

/** Register the routes of the plugin. */
export function registerRoutes(
  ctx: PluginContext,
  webServer: WebServerService,
  sidecar: NapCatSidecar,
  bridge: ChatBridge,
  workspace: string,
  uin: string,
  connected: () => boolean,
  logger: PluginLogger,
  config: Config,
): () => void {
  const disposers: Array<() => void> = []

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: ROUTE_PREFIX,
      handler: (_request, response) => {
        sendHtml(response, 200, PAGE)
      },
    }),
  )

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: `${ROUTE_PREFIX}/state`,
      handler: async (_request, response) => {
        const snapshot: StatusSnapshot = {
          sidecar: await sidecar.inspect(),
          bridge: {
            chats: Object.keys(bridge.state.chats).length,
            connected: connected(),
            uin,
          },
          workspace,
          log: sidecar.log.slice(-80),
        }
        sendJson(response, 200, snapshot)
      },
    }),
  )

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: `${ROUTE_PREFIX}/settings`,
      handler: async (request, response) => {
        if (request.method !== 'POST') {
          let persona = config.persona
          try {
            persona = personaText(await readFile(join(config.workspaceDir, PERSONA_FILE), 'utf8'))
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
              logger.warn(`dsh-luoyu: cannot read the persona file: ${(error as Error).message}`)
            }
          }
          sendJson(response, 200, {
            workspaceDir: config.workspaceDir,
            persona,
            privateReply: config.privateReply,
            groupReply: normalizeGroupReplyMode(config.groupReply),
          })
          return
        }

        let payload: unknown
        try {
          payload = JSON.parse(await readBody(request))
        } catch (error) {
          const tooLarge = (error as Error).message === 'The request body is too large.'
          sendJson(response, tooLarge ? 413 : 400, { error: tooLarge ? (error as Error).message : 'The settings body must be valid JSON.' })
          return
        }
        if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
          sendJson(response, 400, { error: 'The settings body must be an object.' })
          return
        }
        const input = payload as Record<string, unknown>
        const patch: Partial<Config> = {}
        if (input.workspaceDir !== undefined) {
          if (typeof input.workspaceDir !== 'string' || input.workspaceDir.trim().length === 0) {
            sendJson(response, 400, { error: 'workspaceDir must be a non-empty path.' })
            return
          }
          const workspaceDir = input.workspaceDir.trim()
          patch.workspaceDir = isAbsolute(workspaceDir) ? workspaceDir : resolve(workspaceDir)
        }
        if (input.persona !== undefined) {
          if (typeof input.persona !== 'string' || input.persona.trim().length === 0 || input.persona.length > 50_000) {
            sendJson(response, 400, { error: 'persona must contain between 1 and 50000 characters.' })
            return
          }
          patch.persona = input.persona.trim()
        }
        if (input.privateReply !== undefined) {
          if (typeof input.privateReply !== 'boolean') {
            sendJson(response, 400, { error: 'privateReply must be a boolean.' })
            return
          }
          patch.privateReply = input.privateReply
        }
        if (input.groupReply !== undefined) {
          if (input.groupReply !== 'mention' && input.groupReply !== 'balanced') {
            sendJson(response, 400, { error: 'groupReply must be "mention" or "balanced".' })
            return
          }
          patch.groupReply = input.groupReply
        }
        if (Object.keys(patch).length === 0) {
          sendJson(response, 400, { error: 'No supported settings were supplied.' })
          return
        }

        const editor = optionalService<ConfigEditorService>(ctx, 'configEditor')
        const entry = editor?.entries().find(row => row.options.id === 'dsh-luoyu')
        if (editor === undefined || entry === undefined) {
          sendJson(response, 503, { error: 'The active profile does not expose an editable Luoyu configuration.' })
          return
        }

        const next = resolveConfig({ ...config, ...patch })
        let personaPath: string | undefined
        let oldPersona: Buffer | undefined
        let hadPersona = false
        if (patch.persona !== undefined) {
          personaPath = join(next.workspaceDir, PERSONA_FILE)
          try {
            oldPersona = await readFile(personaPath)
            hadPersona = true
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
              sendJson(response, 500, { error: 'The existing persona file cannot be read.' })
              return
            }
          }
          try {
            await mkdir(dirname(personaPath), { recursive: true })
            await writeFile(personaPath, `${personaBody(next.persona).trimEnd()}\n`, { encoding: 'utf8', mode: 0o600 })
          } catch (error) {
            sendJson(response, 500, { error: `The persona file cannot be written: ${(error as Error).message}` })
            return
          }
        }

        try {
          await editor.edit(entry as ConfigEntryLike, current => ({ ...current, ...patch }))
          sendJson(response, 200, { saved: true, workspaceChanged: next.workspaceDir !== config.workspaceDir })
        } catch (error) {
          if (personaPath !== undefined) {
            if (hadPersona && oldPersona !== undefined) await writeFile(personaPath, oldPersona, { mode: 0o600 }).catch(() => undefined)
            else await rm(personaPath, { force: true }).catch(() => undefined)
          }
          logger.warn(`dsh-luoyu: cannot save settings: ${(error as Error).message}`)
          sendJson(response, 500, { error: (error as Error).message })
        }
      },
    }),
  )

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: `${ROUTE_PREFIX}/qrcode`,
      handler: async (_request, response) => {
        const path = sidecar.current.qrcodePath
        if (path === undefined) {
          sendJson(response, 404, { error: 'no QR code yet' })
          return
        }
        try {
          const data = await readFile(path)
          response.statusCode = 200
          response.setHeader('content-type', 'image/png')
          response.setHeader('cache-control', 'no-store')
          response.end(data)
        } catch {
          sendJson(response, 404, { error: 'the QR code file is not readable' })
        }
      },
    }),
  )

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: `${ROUTE_PREFIX}/start`,
      handler: async (_request, response) => {
        try {
          const phase = await sidecar.start()
          sendJson(response, 200, { phase })
        } catch (error) {
          logger.warn(`dsh-luoyu: cannot start NapCat: ${(error as Error).message}`)
          sendJson(response, 500, { error: (error as Error).message })
        }
      },
    }),
  )

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: `${ROUTE_PREFIX}/stop`,
      handler: async (_request, response) => {
        await sidecar.stop()
        sendJson(response, 200, { phase: sidecar.current.phase })
      },
    }),
  )

  disposers.push(
    webServer.register({
      kind: 'exact',
      path: `${ROUTE_PREFIX}/refresh-qrcode`,
      handler: async (_request, response) => {
        try {
          await sidecar.refreshQrcode()
          sendJson(response, 200, { phase: sidecar.current.phase })
        } catch (error) {
          sendJson(response, 500, { error: (error as Error).message })
        }
      },
    }),
  )

  logger.info(`dsh-luoyu: status page at ${ROUTE_PREFIX}`)
  return () => {
    for (const dispose of disposers) dispose()
  }
}

/** Find the Harness web server, when the profile has one. */
export function findWebServer(ctx: PluginContext): WebServerService | undefined {
  return optionalService<WebServerService>(ctx, 'webServer')
}

/** Read one request body. Exported for the tests. */
export { readBody }
