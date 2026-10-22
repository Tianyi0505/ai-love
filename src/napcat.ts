/**
 * NapCat sidecar manager.
 *
 * NapCat is the bridge between the QQ client and the OneBot protocol. It does
 * not speak the QQ protocol itself: it loads the official QQ client and hooks
 * it. The manager therefore has two external dependencies that it cannot
 * supply — the QQ client and, on a Linux host without a display, a virtual
 * display server.
 *
 * The manager downloads NapCat, writes the OneBot configuration, starts the
 * process, and reports the login state. Every step that needs a missing
 * dependency stops with an actionable message instead of a stack trace.
 *
 * @module dsh-luoyu/napcat
 */

import { spawn, type ChildProcess } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import { access, chmod, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { pipeline } from 'node:stream/promises'
import { Readable } from 'node:stream'
import type { PluginLogger } from './context.ts'

/** The release host of the NapCat project. */
const RELEASE_API = 'https://api.github.com/repos/NapNeko/NapCatQQ/releases'

/** The asset that carries the portable NapCat shell for every platform. */
const SHELL_ASSET = 'NapCat.Shell.zip'

/** Candidate directories of a Linux QQ installation. */
const LINUX_QQ_CANDIDATES = [
  '/opt/QQ',
  '/opt/qq',
  '/usr/lib/qq',
  '/usr/share/qq',
  '/usr/local/QQ',
]

/** One step of the login flow. */
export type LoginPhase =
  | 'unknown'
  | 'not-installed'
  | 'needs-qq'
  | 'needs-display'
  | 'starting'
  | 'waiting-qrcode'
  | 'qrcode-ready'
  | 'scanned'
  | 'online'
  | 'offline'
  | 'failed'

/** The state that the web page renders. */
export interface SidecarStatus {
  /** Current login phase. */
  phase: LoginPhase
  /** True when the NapCat process runs. */
  running: boolean
  /** True when the managed installation exists. */
  installed: boolean
  /** Installed NapCat version, when known. */
  version: string | undefined
  /** QQ client directory that NapCat uses. */
  qqPath: string | undefined
  /** Message for the operator. */
  detail: string
  /** Path of the QR code image, when one exists. */
  qrcodePath: string | undefined
  /** Unix epoch milliseconds of the last change. */
  updatedAt: number
  /** QQ number of the logged-in account, when known. */
  uin: string | undefined
  /** Nickname of the logged-in account, when known. */
  nickname: string | undefined
}

/** Settings for the managed sidecar. */
export interface SidecarOptions {
  /** Directory that holds the installation, the configuration, and the cache. */
  napcatDir: string
  /** Release tag, or `latest`. */
  version: string
  /** Port of the OneBot WebSocket server. */
  wsPort: number
  /** Port of the OneBot HTTP server. */
  httpPort: number
  /** Access token for both OneBot endpoints. */
  accessToken: string
  /** QQ number, used as the configuration file name. */
  uin: string
  /** Port of the NapCat web interface. */
  webuiPort: number
  /** Token of the NapCat web interface. */
  webuiToken: string
  /** Start the sidecar on plugin start. */
  autoStart: boolean
}

/** The error that a missing dependency raises. */
export class SidecarDependencyError extends Error {
  readonly phase: LoginPhase

  constructor(phase: LoginPhase, message: string) {
    super(message)
    this.name = 'SidecarDependencyError'
    this.phase = phase
  }
}

/** True when the path exists. */
async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

/** Find the directory of the installed QQ client. */
export async function detectQq(): Promise<string | undefined> {
  for (const candidate of LINUX_QQ_CANDIDATES) {
    if (await exists(join(candidate, 'resources', 'app', 'package.json'))) return candidate
  }
  return undefined
}

/**
 * Report whether a display server is available.
 *
 * NapCat loads the QQ client, which is an Electron application. Without
 * `DISPLAY` or `WAYLAND_DISPLAY` the client cannot start.
 */
export function hasDisplay(): boolean {
  return (process.env.DISPLAY ?? '').length > 0 || (process.env.WAYLAND_DISPLAY ?? '').length > 0
}

/** Read the release tag and the download URL of the shell asset. */
async function resolveRelease(version: string): Promise<{ tag: string; url: string }> {
  const endpoint = version === 'latest' ? `${RELEASE_API}/latest` : `${RELEASE_API}/tags/${version}`
  const response = await fetch(endpoint, {
    headers: { accept: 'application/vnd.github+json', 'user-agent': 'dsh-luoyu' },
  })
  if (!response.ok) {
    throw new Error(`cannot read the NapCat release "${version}": HTTP ${response.status}`)
  }
  const body = (await response.json()) as {
    tag_name?: string
    assets?: Array<{ name?: string; browser_download_url?: string }>
  }
  const tag = body.tag_name ?? version
  const asset = (body.assets ?? []).find(entry => entry.name === SHELL_ASSET)
  if (asset?.browser_download_url === undefined) {
    throw new Error(`the NapCat release "${tag}" has no ${SHELL_ASSET} asset`)
  }
  return { tag, url: asset.browser_download_url }
}

/** Download one file. */
async function download(url: string, target: string): Promise<void> {
  const response = await fetch(url, { redirect: 'follow' })
  if (!response.ok || response.body === null) {
    throw new Error(`cannot download ${url}: HTTP ${response.status}`)
  }
  await pipeline(Readable.fromWeb(response.body as never), createWriteStream(target))
}

/** Extract one zip archive with the system `unzip`. */
async function unzip(archive: string, target: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const child = spawn('unzip', ['-o', '-q', archive, '-d', target], { stdio: 'ignore' })
    child.on('error', reject)
    child.on('close', code => {
      if (code === 0) resolve()
      else reject(new Error(`unzip exited with code ${code}`))
    })
  })
}

/** The OneBot network configuration that NapCat reads. */
export interface OneBotConfig {
  network: {
    httpServers: Array<Record<string, unknown>>
    httpSseServers: Array<Record<string, unknown>>
    httpClients: Array<Record<string, unknown>>
    websocketServers: Array<Record<string, unknown>>
    websocketClients: Array<Record<string, unknown>>
    plugins: Array<Record<string, unknown>>
  }
  musicSignUrl: string
  enableLocalFile2Url: boolean
  parseMultMsg: boolean
  imageDownloadProxy: string
  timeout: { baseTimeout: number; uploadSpeedKBps: number; downloadSpeedKBps: number; maxTimeout: number }
}

/**
 * Build the OneBot configuration.
 *
 * The plugin talks to the WebSocket server for events and to the HTTP server
 * for actions. Both listen on the loopback address and share one token.
 *
 * @param options - the sidecar settings.
 * @returns the configuration object.
 */
export function buildOneBotConfig(options: SidecarOptions): OneBotConfig {
  return {
    network: {
      httpServers: [
        {
          name: 'dsh-luoyu-http',
          enable: true,
          port: options.httpPort,
          host: '127.0.0.1',
          enableCors: true,
          enableWebsocket: false,
          messagePostFormat: 'array',
          token: options.accessToken,
          debug: false,
        },
      ],
      httpSseServers: [],
      httpClients: [],
      websocketServers: [
        {
          name: 'dsh-luoyu-ws',
          enable: true,
          host: '127.0.0.1',
          port: options.wsPort,
          messagePostFormat: 'array',
          reportSelfMessage: false,
          token: options.accessToken,
          enableForcePushEvent: true,
          debug: false,
          heartInterval: 30_000,
        },
      ],
      websocketClients: [],
      plugins: [],
    },
    musicSignUrl: '',
    enableLocalFile2Url: false,
    parseMultMsg: false,
    imageDownloadProxy: '',
    timeout: {
      baseTimeout: 10_000,
      uploadSpeedKBps: 256,
      downloadSpeedKBps: 256,
      maxTimeout: 1_800_000,
    },
  }
}

/** The managed NapCat installation. */
export class NapCatSidecar {
  private readonly options: SidecarOptions
  private readonly logger: PluginLogger
  private child: ChildProcess | undefined
  private status: SidecarStatus
  private pollTimer: NodeJS.Timeout | undefined
  private logTail: string[] = []

  constructor(options: SidecarOptions, logger: PluginLogger) {
    this.options = options
    this.logger = logger
    this.status = {
      phase: 'unknown',
      running: false,
      installed: false,
      version: undefined,
      qqPath: undefined,
      detail: 'Not started yet.',
      qrcodePath: undefined,
      updatedAt: Date.now(),
      uin: undefined,
      nickname: undefined,
    }
  }

  /** The current status. */
  get current(): SidecarStatus {
    return this.status
  }

  /** Path of the entry script. */
  private get entryPath(): string {
    return join(this.options.napcatDir, 'napcat.mjs')
  }

  /** Path of the version marker that the manager writes. */
  private get versionPath(): string {
    return join(this.options.napcatDir, 'installed-version.txt')
  }

  /** Path of the OneBot configuration for the configured account. */
  private get configPath(): string {
    const name = this.options.uin.length > 0 ? `onebot11_${this.options.uin}.json` : 'onebot11.json'
    return join(this.options.napcatDir, 'config', name)
  }

  /** Path of the QR code that NapCat writes. */
  private get qrcodePath(): string {
    return join(this.options.napcatDir, 'cache', 'qrcode.png')
  }

  /** Change the status and stamp the time. */
  private setStatus(patch: Partial<SidecarStatus>): void {
    this.status = { ...this.status, ...patch, updatedAt: Date.now() }
  }

  /**
   * Download NapCat when it is absent.
   *
   * @returns the installed version.
   */
  async install(): Promise<string> {
    if (await exists(this.entryPath)) {
      const installed = await readFile(this.versionPath, 'utf8').catch(() => 'unknown')
      this.setStatus({ installed: true, version: installed.trim(), phase: 'unknown' })
      return installed.trim()
    }
    const release = await resolveRelease(this.options.version)
    await mkdir(this.options.napcatDir, { recursive: true })
    const archive = join(this.options.napcatDir, 'napcat.zip')
    this.logger.info(`dsh-luoyu: downloading NapCat ${release.tag}`)
    await download(release.url, archive)
    await unzip(archive, this.options.napcatDir)
    await rm(archive, { force: true })
    await writeFile(this.versionPath, `${release.tag}\n`, 'utf8')
    this.setStatus({ installed: true, version: release.tag })
    this.logger.info(`dsh-luoyu: NapCat ${release.tag} installed in ${this.options.napcatDir}`)
    return release.tag
  }

  /** Write the OneBot configuration that the plugin needs. */
  async writeConfig(): Promise<void> {
    await mkdir(join(this.options.napcatDir, 'config'), { recursive: true })
    const config = buildOneBotConfig(this.options)
    await writeFile(this.configPath, `${JSON.stringify(config, undefined, 2)}\n`, 'utf8')
    this.logger.info(`dsh-luoyu: wrote the OneBot configuration to ${this.configPath}`)
  }

  /**
   * Check the dependencies that the manager cannot supply.
   *
   * @throws SidecarDependencyError when a dependency is absent.
   */
  async checkDependencies(): Promise<void> {
    const qq = await detectQq()
    if (qq === undefined) {
      throw new SidecarDependencyError(
        'needs-qq',
        'The QQ client is not installed. NapCat loads the official QQ client, so the host needs a Linux QQ installation. Install the deb package from https://im.qq.com/linuxqq/ and start the plugin again.',
      )
    }
    this.setStatus({ qqPath: qq })
    if (process.platform === 'linux' && !hasDisplay()) {
      throw new SidecarDependencyError(
        'needs-display',
        'No display server is available. The QQ client is an Electron application and needs a display. Install Xvfb and start the plugin under `xvfb-run`, or run it on a host with a desktop session.',
      )
    }
  }

  /**
   * Install, configure, and start the sidecar.
   *
   * @returns the login phase after the start.
   */
  async start(): Promise<LoginPhase> {
    if (this.child !== undefined) return this.status.phase
    await this.install()
    await this.checkDependencies()
    await this.writeConfig()
    this.setStatus({ phase: 'starting', detail: 'NapCat is starting.' })

    const child = spawn(process.execPath, [this.entryPath], {
      cwd: this.options.napcatDir,
      env: {
        ...process.env,
        NAPCAT_WORKDIR: this.options.napcatDir,
        NAPCAT_WEBUI_PREFERRED_PORT: String(this.options.webuiPort),
        ...(this.options.webuiToken.length > 0 ? { NAPCAT_WEBUI_SECRET_KEY: this.options.webuiToken } : {}),
        ...(this.options.uin.length > 0 ? { NAPCAT_QUICK_ACCOUNT: this.options.uin } : {}),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    this.child = child
    this.setStatus({ running: true, phase: 'starting', detail: 'NapCat is starting.' })

    const record = (chunk: Buffer): void => {
      for (const line of chunk.toString().split('\n')) {
        const trimmed = line.trim()
        if (trimmed.length === 0) continue
        this.logTail.push(trimmed)
        if (this.logTail.length > 200) this.logTail.shift()
        this.observeLog(trimmed)
      }
    }
    child.stdout?.on('data', record)
    child.stderr?.on('data', record)

    child.on('exit', (code, signal) => {
      this.child = undefined
      this.setStatus({
        running: false,
        phase: code === 0 ? 'offline' : 'failed',
        detail: `NapCat exited with ${signal ?? `code ${code}`}.`,
      })
      this.logger.warn(`dsh-luoyu: NapCat exited with ${signal ?? `code ${code}`}`)
    })

    this.startLoginPolling()
    return this.status.phase
  }

  /** Read the process output and update the login phase. */
  private observeLog(line: string): void {
    if (line.includes('二维码') || line.includes('qrcode') || line.includes('QRCode')) {
      this.setStatus({ phase: 'qrcode-ready', detail: 'Scan the QR code with the QQ mobile app.', qrcodePath: this.qrcodePath })
      return
    }
    if (line.includes('登录成功') || line.includes('LoginSucceed') || line.includes('已登录')) {
      this.setStatus({ phase: 'online', detail: 'The QQ account is online.' })
      return
    }
    if (line.includes('启动失败') || line.includes('Error:')) {
      this.setStatus({ phase: 'failed', detail: line.slice(0, 400) })
    }
  }

  /** Poll the web interface for the login state. */
  private startLoginPolling(): void {
    if (this.pollTimer !== undefined) return
    const tick = async (): Promise<void> => {
      if (this.child === undefined) return
      try {
        const info = await this.webui('POST', '/api/QQLogin/GetQQLoginInfo', {})
        const data = info as { uin?: string | number; nick?: string; online?: boolean } | undefined
        if (data !== undefined && data.uin !== undefined && String(data.uin).length > 0) {
          this.setStatus({
            uin: String(data.uin),
            nickname: typeof data.nick === 'string' ? data.nick : undefined,
            phase: data.online === true ? 'online' : 'scanned',
            detail: data.online === true ? 'The QQ account is online.' : 'The QR code was scanned.',
          })
        }
      } catch {
        // The web interface answers only after the QQ client starts. A failed
        // poll is expected during startup, so it changes nothing.
      }
      if (await exists(this.qrcodePath)) {
        if (this.status.phase !== 'online') {
          this.setStatus({ qrcodePath: this.qrcodePath, phase: this.status.phase === 'scanned' ? 'scanned' : 'qrcode-ready' })
        }
      }
    }
    this.pollTimer = setInterval(() => {
      void tick()
    }, 3000)
    this.pollTimer.unref?.()
  }

  /** Call one web interface route. */
  async webui(method: 'GET' | 'POST', path: string, body: unknown): Promise<unknown> {
    const url = `http://127.0.0.1:${this.options.webuiPort}${path}`
    const headers: Record<string, string> = { 'content-type': 'application/json' }
    if (this.options.webuiToken.length > 0) headers.Authorization = `Bearer ${this.options.webuiToken}`
    const response = await fetch(url, {
      method,
      headers,
      ...(method === 'POST' ? { body: JSON.stringify(body) } : {}),
    })
    const text = await response.text()
    if (!response.ok) throw new Error(`NapCat web interface returned HTTP ${response.status}`)
    const parsed = JSON.parse(text) as { code?: number; data?: unknown; message?: string }
    if (parsed.code !== undefined && parsed.code !== 0) {
      throw new Error(parsed.message ?? `NapCat web interface returned code ${parsed.code}`)
    }
    return parsed.data
  }

  /** Ask NapCat for a new QR code. */
  async refreshQrcode(): Promise<void> {
    await this.webui('POST', '/api/QQLogin/GetQQLoginQrcode', {})
    this.setStatus({ phase: 'waiting-qrcode', detail: 'Requesting a new QR code.' })
  }

  /** The recent process output, for the status page. */
  get log(): readonly string[] {
    return this.logTail
  }

  /** Stop the process and the polling. */
  async stop(): Promise<void> {
    if (this.pollTimer !== undefined) {
      clearInterval(this.pollTimer)
      this.pollTimer = undefined
    }
    const child = this.child
    this.child = undefined
    if (child === undefined) {
      this.setStatus({ running: false })
      return
    }
    await new Promise<void>(resolve => {
      const timer = setTimeout(() => {
        child.kill('SIGKILL')
        resolve()
      }, 10_000)
      timer.unref?.()
      child.once('exit', () => {
        clearTimeout(timer)
        resolve()
      })
      child.kill('SIGTERM')
    })
    this.setStatus({ running: false, phase: 'offline', detail: 'NapCat is stopped.' })
  }

  /** Read the installation facts without starting anything. */
  async inspect(): Promise<SidecarStatus> {
    const installed = await exists(this.entryPath)
    const version = installed ? (await readFile(this.versionPath, 'utf8').catch(() => '')).trim() : undefined
    const qq = await detectQq()
    const qrcode = (await exists(this.qrcodePath)) ? this.qrcodePath : undefined
    let phase: LoginPhase = this.status.phase
    let detail = this.status.detail
    if (!installed) {
      phase = 'not-installed'
      detail = 'NapCat is not installed. Start the plugin to download it.'
    } else if (qq === undefined) {
      phase = 'needs-qq'
      detail = 'The QQ client is not installed on this host.'
    } else if (process.platform === 'linux' && !hasDisplay()) {
      phase = 'needs-display'
      detail = 'No display server is available for the QQ client.'
    }
    this.setStatus({ installed, version, qqPath: qq, qrcodePath: qrcode, phase, detail })
    return this.status
  }

  /** List the files of the installation, for diagnostics. */
  async listInstallation(): Promise<string[]> {
    try {
      const entries = await readdir(this.options.napcatDir)
      return entries.sort()
    } catch {
      return []
    }
  }

  /** Size of the installation in bytes. */
  async installationSize(): Promise<number> {
    const target = join(this.options.napcatDir, 'napcat.mjs')
    try {
      const info = await stat(target)
      await chmod(target, 0o644).catch(() => undefined)
      return info.size
    } catch {
      return 0
    }
  }
}
