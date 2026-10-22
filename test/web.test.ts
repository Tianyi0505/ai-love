/**
 * Tests of the status routes.
 *
 * The tests register the routes on a stand-in web server, then call the
 * handlers with a stand-in request and response. They do not start NapCat and
 * they do not create a session.
 *
 * @module dsh-ai-love/test/web.test
 */

import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import type { PluginContext, PluginLogger, WebRequest, WebResponse, WebRoute, WebServerService } from '../src/context.ts'
import { ROUTE_PREFIX, findWebServer, readBody, registerRoutes } from '../src/web.ts'
import { resolveConfig } from '../src/config.ts'
import { personaBody } from '../src/workspace.ts'
import type { ChatBridge } from '../src/bridge.ts'
import type { NapCatSidecar, SidecarStatus } from '../src/napcat.ts'

const config = resolveConfig({})

const silent: PluginLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
}

/** A web server that records the routes. */
class FakeWebServer implements WebServerService {
  readonly routes = new Map<string, WebRoute>()

  register(route: WebRoute): () => void {
    this.routes.set(route.path, route)
    return () => {
      this.routes.delete(route.path)
    }
  }

  getOrigin(): string {
    return 'http://127.0.0.1:3080'
  }
}

/** The captured response of one handler call. */
interface Captured {
  status: number
  headers: Record<string, string>
  body: string
}

/** A request that emits the given chunks. */
function requestOf(chunks: readonly string[], method = 'GET'): WebRequest {
  const emitter = new EventEmitter() as unknown as WebRequest & EventEmitter
  Object.assign(emitter, { method })
  setImmediate(() => {
    for (const chunk of chunks) emitter.emit('data', Buffer.from(chunk))
    emitter.emit('end')
  })
  return emitter
}

/** A response that records what the handler writes. */
function responseOf(): { response: WebResponse; captured: Captured } {
  const captured: Captured = { status: 200, headers: {}, body: '' }
  const response: WebResponse = {
    get statusCode() {
      return captured.status
    },
    set statusCode(value: number) {
      captured.status = value
    },
    setHeader(name: string, value: string) {
      captured.headers[name.toLowerCase()] = value
    },
    end(body?: string | Uint8Array) {
      captured.body = typeof body === 'string' ? body : body === undefined ? '' : Buffer.from(body).toString('utf8')
    },
  }
  return { response, captured }
}

/** A sidecar that answers with a fixed status. */
function sidecarOf(status: SidecarStatus): NapCatSidecar {
  return {
    inspect: async () => status,
    get current() {
      return status
    },
    get log() {
      return ['line one', 'line two']
    },
    start: async () => 'starting',
    stop: async () => undefined,
    refreshQrcode: async () => undefined,
  } as unknown as NapCatSidecar
}

/** A bridge with one chat. */
function bridgeOf(): ChatBridge {
  return {
    state: { version: 1, chats: { 'group:1': { sessionId: 's', kind: 'group', targetId: '1', title: 'g', updatedAt: 1 } }, seenMessageIds: [] },
  } as unknown as ChatBridge
}

/** The status that the stand-in sidecar reports. */
function statusOf(patch: Partial<SidecarStatus> = {}): SidecarStatus {
  return {
    phase: 'online',
    running: true,
    installed: true,
    version: 'v4.18.41',
    qqPath: '/opt/QQ',
    detail: 'The QQ account is online.',
    qrcodePath: undefined,
    updatedAt: 1,
    uin: '3916750998',
    nickname: 'Ada',
    ...patch,
  }
}

/** Register the routes and return the fake server. */
function setup(status: SidecarStatus = statusOf()): FakeWebServer {
  const server = new FakeWebServer()
  registerRoutes(
    { logger: silent } as unknown as PluginContext,
    server,
    sidecarOf(status),
    bridgeOf(),
    '/tmp/workspace',
    '3916750998',
    () => true,
    silent,
    config,
  )
  return server
}

test('registers the page and the action routes', () => {
  const server = setup()
  assert.deepEqual(
    [...server.routes.keys()].sort(),
    [
      ROUTE_PREFIX,
      `${ROUTE_PREFIX}/qrcode`,
      `${ROUTE_PREFIX}/refresh-qrcode`,
      `${ROUTE_PREFIX}/start`,
      `${ROUTE_PREFIX}/settings`,
      `${ROUTE_PREFIX}/state`,
      `${ROUTE_PREFIX}/stop`,
    ].sort(),
  )
})

test('serves the page as HTML', async () => {
  const server = setup()
  const route = server.routes.get(ROUTE_PREFIX)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 200)
  assert.match(captured.headers['content-type'] ?? '', /text\/html/)
  assert.match(captured.body, /dsh-ai-love/)
})

test('reports the state as JSON', async () => {
  const server = setup()
  const route = server.routes.get(`${ROUTE_PREFIX}/state`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 200)
  assert.match(captured.headers['content-type'] ?? '', /application\/json/)
  const body = JSON.parse(captured.body) as {
    sidecar: SidecarStatus
    bridge: { chats: number; connected: boolean; uin: string }
    workspace: string
    log: string[]
  }
  assert.equal(body.sidecar.phase, 'online')
  assert.equal(body.bridge.chats, 1)
  assert.equal(body.bridge.connected, true)
  assert.equal(body.bridge.uin, '3916750998')
  assert.equal(body.workspace, '/tmp/workspace')
  assert.deepEqual(body.log, ['line one', 'line two'])
})

test('returns the current profile settings as JSON', async () => {
  const server = setup()
  const route = server.routes.get(`${ROUTE_PREFIX}/settings`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 200)
  assert.deepEqual(JSON.parse(captured.body), {
    workspaceDir: config.workspaceDir,
    persona: config.persona,
    privateReply: config.privateReply,
    groupReply: config.groupReply,
  })
})

test('returns the persona text stored in the workspace file', async () => {
  const workspaceDir = await mkdtemp(join(tmpdir(), 'dsh-ai-love-settings-read-'))
  const current = resolveConfig({ ...config, workspaceDir, persona: 'Profile default.' })
  await writeFile(join(workspaceDir, 'PERSONA.md'), personaBody('Edited in the workspace.'), 'utf8')
  const ctx = { logger: silent, get: () => undefined } as unknown as PluginContext
  const server = new FakeWebServer()
  registerRoutes(ctx, server, sidecarOf(statusOf()), bridgeOf(), workspaceDir, current.uin, () => true, silent, current)
  const route = server.routes.get(`${ROUTE_PREFIX}/settings`)
  assert.ok(route !== undefined)
  try {
    const { response, captured } = responseOf()
    await route.handler(requestOf([]), response)
    assert.equal(JSON.parse(captured.body).persona, 'Edited in the workspace.')
  } finally {
    await rm(workspaceDir, { recursive: true, force: true })
  }
})

test('persists settings through the profile editor and updates the persona file', async () => {
  const workspaceDir = await mkdtemp(join(tmpdir(), 'dsh-ai-love-settings-'))
  let saved: Record<string, unknown> | undefined
  const entry = { options: { id: 'dsh-ai-love', config: {} } }
  const editor = {
    entries: () => [entry],
    edit: async (_entry: unknown, change: (current: Record<string, unknown>, inherited: Record<string, unknown>) => Record<string, unknown>) => {
      saved = change(config as unknown as Record<string, unknown>, {})
    },
  }
  const ctx = { logger: silent, get: (name: string) => name === 'configEditor' ? editor : undefined } as unknown as PluginContext
  const server = new FakeWebServer()
  registerRoutes(ctx, server, sidecarOf(statusOf()), bridgeOf(), config.workspaceDir, config.uin, () => true, silent, config)
  const route = server.routes.get(`${ROUTE_PREFIX}/settings`)
  assert.ok(route !== undefined)
  try {
    const { response, captured } = responseOf()
    await route.handler(requestOf([JSON.stringify({ workspaceDir, persona: 'A new persona.', privateReply: false, groupReply: 'all' })], 'POST'), response)
    assert.equal(captured.status, 200)
    assert.deepEqual(JSON.parse(captured.body), { saved: true, workspaceChanged: true })
    assert.equal(saved?.workspaceDir, workspaceDir)
    assert.equal(saved?.persona, 'A new persona.')
    assert.equal(saved?.privateReply, false)
    assert.equal(saved?.groupReply, 'all')
    assert.match(await readFile(join(workspaceDir, 'PERSONA.md'), 'utf8'), /A new persona\./)
  } finally {
    await rm(workspaceDir, { recursive: true, force: true })
  }
})

test('answers 404 when there is no QR code', async () => {
  const server = setup()
  const route = server.routes.get(`${ROUTE_PREFIX}/qrcode`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 404)
  assert.match(captured.body, /no QR code/)
})

test('serves the QR code image when the file exists', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-ai-love-web-'))
  const path = join(dir, 'qrcode.png')
  const bytes = Buffer.from([0x89, 0x50, 0x4e, 0x47])
  await writeFile(path, bytes)
  try {
    const server = setup(statusOf({ qrcodePath: path }))
    const route = server.routes.get(`${ROUTE_PREFIX}/qrcode`)
    assert.ok(route !== undefined)
    const { response, captured } = responseOf()
    await route.handler(requestOf([]), response)
    assert.equal(captured.status, 200)
    assert.equal(captured.headers['content-type'], 'image/png')
    assert.equal(captured.headers['cache-control'], 'no-store')
    assert.equal(captured.body, bytes.toString('utf8'))
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})

test('reports the phase that a start returns', async () => {
  const server = setup()
  const route = server.routes.get(`${ROUTE_PREFIX}/start`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 200)
  assert.deepEqual(JSON.parse(captured.body), { phase: 'starting' })
})

test('reports a start failure as a JSON error', async () => {
  const server = new FakeWebServer()
  const failing = {
    inspect: async () => statusOf(),
    current: statusOf(),
    log: [],
    start: async () => {
      throw new Error('the QQ client is not installed')
    },
    stop: async () => undefined,
    refreshQrcode: async () => undefined,
  } as unknown as NapCatSidecar
  registerRoutes(
    { logger: silent } as unknown as PluginContext,
    server,
    failing,
    bridgeOf(),
    '/tmp/workspace',
    '1',
    () => false,
    silent,
    config,
  )
  const route = server.routes.get(`${ROUTE_PREFIX}/start`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 500)
  assert.match(captured.body, /the QQ client is not installed/)
})

test('reports the phase after a stop', async () => {
  const server = setup()
  const route = server.routes.get(`${ROUTE_PREFIX}/stop`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 200)
  assert.deepEqual(JSON.parse(captured.body), { phase: 'online' })
})

test('reports a QR code refresh failure as a JSON error', async () => {
  const server = new FakeWebServer()
  const failing = {
    inspect: async () => statusOf(),
    current: statusOf(),
    log: [],
    start: async () => 'starting',
    stop: async () => undefined,
    refreshQrcode: async () => {
      throw new Error('the web interface is not ready')
    },
  } as unknown as NapCatSidecar
  registerRoutes(
    { logger: silent } as unknown as PluginContext,
    server,
    failing,
    bridgeOf(),
    '/tmp/workspace',
    '1',
    () => false,
    silent,
    config,
  )
  const route = server.routes.get(`${ROUTE_PREFIX}/refresh-qrcode`)
  assert.ok(route !== undefined)
  const { response, captured } = responseOf()
  await route.handler(requestOf([]), response)
  assert.equal(captured.status, 500)
  assert.match(captured.body, /the web interface is not ready/)
})

test('removes every route on dispose', () => {
  const server = new FakeWebServer()
  const dispose = registerRoutes(
    { logger: silent } as unknown as PluginContext,
    server,
    sidecarOf(statusOf()),
    bridgeOf(),
    '/tmp/workspace',
    '1',
    () => true,
    silent,
    config,
  )
  assert.equal(server.routes.size, 7)
  dispose()
  assert.equal(server.routes.size, 0)
})

test('reads the body of a request in order', async () => {
  assert.equal(await readBody(requestOf(['one', 'two'])), 'onetwo')
})

test('rejects a request body that exceeds its byte limit', async () => {
  await assert.rejects(readBody(requestOf(['12345']), 4), /request body is too large/)
})

test('finds the web server through the context', () => {
  const server = new FakeWebServer()
  const ctx = {
    get: (name: string) => (name === 'webServer' ? server : undefined),
  } as unknown as PluginContext
  assert.equal(findWebServer(ctx), server)
})

test('reports no web server when the profile has none', () => {
  const ctx = { get: () => undefined } as unknown as PluginContext
  assert.equal(findWebServer(ctx), undefined)
})
