import { timingSafeEqual } from 'node:crypto'
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'
import type { ConversationInput, ConversationOutput, ConversationRuntime } from './conversation-runtime.ts'

interface IngressOptions {
  host: string
  port: number
  token?: string
}

const MAX_BODY_BYTES = 1024 * 1024

function authorized(request: IncomingMessage, token: string | undefined): boolean {
  if (!token) return true
  const expected = Buffer.from(`Bearer ${token}`)
  const actual = Buffer.from(request.headers.authorization ?? '')
  return expected.length === actual.length && timingSafeEqual(expected, actual)
}

function send(response: ServerResponse, status: number, value: unknown): void {
  const body = JSON.stringify(value)
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(body) })
  response.end(body)
}

async function readJson(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  let length = 0
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    length += buffer.length
    if (length > MAX_BODY_BYTES) throw new Error('request body exceeds 1 MiB')
    chunks.push(buffer)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${label} must be a non-empty string`)
  return value
}

export function normalizeConversationInput(value: unknown): ConversationInput {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('request body must be an object')
  const row = value as Record<string, unknown>
  const chat = row.chat !== null && typeof row.chat === 'object' && !Array.isArray(row.chat)
    ? row.chat as Record<string, unknown>
    : undefined
  const sender = row.sender !== null && typeof row.sender === 'object' && !Array.isArray(row.sender)
    ? row.sender as Record<string, unknown>
    : undefined
  const meta = row.meta !== null && typeof row.meta === 'object' && !Array.isArray(row.meta)
    ? row.meta as Record<string, unknown>
    : undefined
  const chatType = String(row.chatType ?? chat?.chat_type ?? '')
  if (chatType !== 'group' && chatType !== 'private') throw new Error('chatType must be group or private')
  return {
    platform: requiredString(row.platform, 'platform'),
    accountId: requiredString(row.accountId ?? row.account_id, 'accountId'),
    chatType,
    chatId: requiredString(row.chatId ?? chat?.chat_id, 'chatId'),
    aiId: typeof (row.aiId ?? meta?.ai_id) === 'string' ? String(row.aiId ?? meta?.ai_id) : undefined,
    senderId: requiredString(row.senderId ?? sender?.user_id, 'senderId'),
    senderName: typeof (row.senderName ?? sender?.name) === 'string' ? String(row.senderName ?? sender?.name) : undefined,
    messageId: typeof (row.messageId ?? row.message_id) === 'string' ? String(row.messageId ?? row.message_id) : undefined,
    text: requiredString(row.text, 'text'),
  }
}

export class HttpIngress {
  private server?: Server
  private readonly runtime: ConversationRuntime
  private readonly options: IngressOptions

  constructor(runtime: ConversationRuntime, options: IngressOptions) {
    this.runtime = runtime
    this.options = options
    const loopback = options.host === '127.0.0.1' || options.host === '::1' || options.host === 'localhost'
    if (!loopback && !options.token) throw new Error('AILOVE_INGRESS_TOKEN is required when ingressHost is not loopback')
  }

  async start(): Promise<void> {
    if (this.server) throw new Error('AI-Love HTTP ingress is already started')
    const server = createServer((request, response) => void this.handle(request, response))
    this.server = server
    await new Promise<void>((resolveStart, rejectStart) => {
      server.once('error', rejectStart)
      server.listen(this.options.port, this.options.host, () => {
        server.off('error', rejectStart)
        resolveStart()
      })
    })
    const address = server.address() as AddressInfo
    process.stdout.write(`AI-Love DSH ingress listening on http://${this.options.host}:${address.port}\n`)
  }

  private async handle(request: IncomingMessage, response: ServerResponse): Promise<void> {
    try {
      if (request.method === 'GET' && request.url === '/healthz') {
        send(response, 200, { status: 'ok' })
        return
      }
      if (request.method !== 'POST' || !['/v1/chat', '/v1/messages'].includes(request.url ?? '')) {
        send(response, 404, { error: 'not found' })
        return
      }
      if (!authorized(request, this.options.token)) {
        send(response, 401, { error: 'unauthorized' })
        return
      }
      const input = normalizeConversationInput(await readJson(request))
      const result: ConversationOutput = await this.runtime.dispatch(input)
      send(response, 200, result)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const status = error instanceof SyntaxError || /must |exceeds /u.test(message) ? 400 : 500
      send(response, status, { error: message })
    }
  }

  async stop(): Promise<void> {
    const server = this.server
    this.server = undefined
    if (!server) return
    await new Promise<void>((resolveStop, rejectStop) => server.close(error => error ? rejectStop(error) : resolveStop()))
  }
}
