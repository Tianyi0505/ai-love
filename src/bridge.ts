/**
 * Chat bridge.
 *
 * The bridge turns one QQ message into one Harness session turn and turns the
 * session answer back into one QQ reply. Each chat keeps one session, so the
 * model sees the history of that chat and nothing else. The workspace holds
 * the memory that every session shares.
 *
 * Messages of one chat run in order. Messages of different chats run in
 * parallel.
 *
 * @module dsh-ai-love/bridge
 */

import { randomUUID } from 'node:crypto'
import type {
  AgentLike,
  PluginContext,
  PluginLogger,
  SessionControllerService,
  SessionEventLike,
  SessionLike,
} from './context.ts'
import { optionalService, requireService } from './context.ts'
import type { GroupReplyMode } from './config.ts'
import { GroupReplyGate, rememberSentMessage, sentMessageId } from './group-rate.ts'
import type { OneBotClient } from './onebot/client.ts'
import { buildOutbound, renderInbound, toPlainChatText } from './onebot/render.ts'
import { segmentsOf, type MessageEvent, type MessageSegment } from './onebot/types.ts'
import { chatKey, markSeen, recordChat, type BridgeState, type StateStore } from './state.ts'

/** The facts that the bridge needs from the configuration. */
export interface BridgeOptions {
  /** Workspace directory that holds the memory and the sessions. */
  workspaceDir: string
  /** Answer private messages. */
  privateReply: boolean
  /** Which group messages the bridge answers. */
  groupReply: GroupReplyMode
  /** Clock used to apply the group reply cadence. */
  now?: () => number
  /** Permission preset for each chat session. */
  permissionPreset: string
  /** IANA time zone for each prompt. */
  timeZone: string
  /** Largest reply, in characters. */
  maxReplyChars: number
  /** Time limit for one turn, in milliseconds. */
  turnTimeoutMs: number
  /** QQ number of the account. */
  uin: string
}

/** One inbound message that the bridge accepted. */
interface InboundJob {
  key: string
  kind: 'private' | 'group'
  targetId: string
  title: string
  messageId: string
  senderName: string
  senderId: string
  text: string
  segments: readonly MessageSegment[]
  directlyAddressed: boolean
  groupReservationAt?: number
}

/** One reply that the bridge collected from a turn. */
interface TurnBuffer {
  turn: number
  text: string
}

/** Largest number of queued messages per chat. */
const MAX_QUEUE_PER_CHAT = 20

/** Format one instant in the configured zone. */
function formatTime(epochMs: number, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat('sv-SE', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(epochMs))
  } catch {
    return new Date(epochMs).toISOString().slice(0, 16).replace('T', ' ')
  }
}

/** Read the text of one assistant message payload. */
function assistantText(data: unknown): string {
  if (data === null || typeof data !== 'object') return ''
  const message = (data as { message?: unknown }).message
  if (message === null || typeof message !== 'object') return ''
  const content = (message as { content?: unknown }).content
  if (!Array.isArray(content)) return ''
  const parts: string[] = []
  for (const block of content) {
    if (block === null || typeof block !== 'object') continue
    const typed = block as { type?: string; text?: string }
    if (typed.type === 'text' && typeof typed.text === 'string') parts.push(typed.text)
  }
  return parts.join('')
}

/** Split one long reply into parts that fit the platform limit. */
export function splitReply(text: string, limit: number): string[] {
  if (limit <= 0 || text.length <= limit) return [text]
  const parts: string[] = []
  let rest = text
  while (rest.length > limit) {
    let cut = rest.lastIndexOf('\n', limit)
    if (cut < Math.floor(limit * 0.5)) cut = rest.lastIndexOf('。', limit)
    if (cut < Math.floor(limit * 0.5)) cut = rest.lastIndexOf('. ', limit)
    if (cut < Math.floor(limit * 0.5)) cut = limit
    parts.push(rest.slice(0, cut).trimEnd())
    rest = rest.slice(cut).trimStart()
  }
  if (rest.length > 0) parts.push(rest)
  return parts
}

/**
 * Build the text of one prompt.
 *
 * The envelope tells the model which chat it answers and who spoke. The body
 * is the transcript of the message.
 *
 * @param job - the accepted message.
 * @param timeZone - the configured time zone.
 * @param receivedAt - the receive instant.
 * @returns the prompt text.
 */
export function buildPrompt(job: InboundJob, timeZone: string, receivedAt: number): string {
  const where = job.kind === 'group' ? `group chat "${job.title}" (group ${job.targetId})` : `private chat with ${job.title} (QQ ${job.targetId})`
  const header = `[QQ ${where} · ${formatTime(receivedAt, timeZone)} ${timeZone}]`
  const body = `${job.senderName} (QQ ${job.senderId}): ${job.text}`
  return `${header}\n${body}`
}

/**
 * The bridge between the QQ account and the Harness sessions.
 */
export class ChatBridge {
  private readonly ctx: PluginContext
  private readonly logger: PluginLogger
  private readonly client: OneBotClient
  private readonly store: StateStore
  private readonly options: BridgeOptions
  private readonly queues = new Map<string, Promise<void>>()
  private readonly queued = new Map<string, number>()
  private readonly buffers = new Map<string, TurnBuffer[]>()
  private readonly waiters = new Map<string, (reason: string) => void>()
  private readonly resolved = new Map<string, AgentLike>()
  private readonly disposed = new Set<string>()
  private readonly groupRate = new GroupReplyGate()
  private readonly sentGroupMessageIds = new Set<string>()
  private closed = false

  constructor(
    ctx: PluginContext,
    client: OneBotClient,
    store: StateStore,
    options: BridgeOptions,
    logger: PluginLogger,
  ) {
    this.ctx = ctx
    this.client = client
    this.store = store
    this.options = options
    this.logger = logger
  }

  /** Subscribe to the session event stream. */
  start(): void {
    this.ctx.on(
      'session/event',
      (session: SessionLike, event: SessionEventLike) => {
        this.observe(session, event)
      },
      { global: true },
    )
  }

  /** Stop accepting messages and wait for the running turns. */
  async close(): Promise<void> {
    this.closed = true
    // A turn that is still running would hold its queue until the timeout. The
    // plugin is shutting down, so settle every waiter now.
    for (const [sessionId, settle] of [...this.waiters]) {
      this.waiters.delete(sessionId)
      settle('closed')
    }
    await Promise.allSettled([...this.queues.values()])
  }

  /**
   * Accept one inbound message event.
   *
   * @param event - the OneBot message event.
   */
  accept(event: MessageEvent): void {
    if (this.closed) return
    const incomingId = event.message_id === undefined ? '' : String(event.message_id)
    if (incomingId.length > 0 && this.store.current.seenMessageIds.includes(incomingId)) return
    const job = this.toJob(event)
    if (job === undefined) return
    const state = this.store.current
    const messageId = job.messageId
    if (messageId.length > 0 && !markSeen(state, messageId)) return
    void this.store.flush()

    const depth = this.queued.get(job.key) ?? 0
    if (depth >= MAX_QUEUE_PER_CHAT) {
      this.groupRate.release(job.key, job.groupReservationAt)
      this.logger.warn(`dsh-ai-love: queue for ${job.key} is full, dropping one message`)
      return
    }
    this.queued.set(job.key, depth + 1)

    const previous = this.queues.get(job.key) ?? Promise.resolve()
    const next = previous
      .then(() => this.handle(job))
      .catch((error: unknown) => {
        this.logger.error(`dsh-ai-love: cannot handle one message of ${job.key}: ${(error as Error).message}`)
      })
      .finally(() => {
        const remaining = (this.queued.get(job.key) ?? 1) - 1
        if (remaining <= 0) {
          this.queued.delete(job.key)
          this.queues.delete(job.key)
        } else {
          this.queued.set(job.key, remaining)
        }
      })
    this.queues.set(job.key, next)
  }

  /** Convert one event into a job, or reject it. */
  private toJob(event: MessageEvent): InboundJob | undefined {
    const selfId = this.options.uin.length > 0 ? this.options.uin : event.self_id === undefined ? '' : String(event.self_id)
    const senderId = event.user_id === undefined ? '' : String(event.user_id)
    if (senderId.length === 0) return undefined
    if (selfId.length > 0 && senderId === selfId) return undefined

    const kind: 'private' | 'group' = event.message_type === 'group' ? 'group' : 'private'
    const groupId = event.group_id === undefined ? '' : String(event.group_id)
    if (kind === 'group' && groupId.length === 0) return undefined

    const rendered = renderInbound(segmentsOf(event))
    if (rendered.empty) return undefined

    const mentioned = selfId.length > 0 && rendered.mentionedUserIds.includes(selfId)
    const quotedOwnMessage = kind === 'group'
      && rendered.replyToMessageId !== undefined
      && this.sentGroupMessageIds.has(rendered.replyToMessageId)
    const directlyAddressed = mentioned || quotedOwnMessage
    if (kind === 'private' && !this.options.privateReply) return undefined

    const targetId = kind === 'group' ? groupId : senderId
    const key = chatKey(kind, targetId)
    let groupReservationAt: number | undefined
    if (kind === 'group') {
      const now = this.options.now?.() ?? Date.now()
      const lastReplyAt = this.store.current.chats[key]?.lastGroupReplyAt
      const recentMessages = this.groupRate.observe(key, now, lastReplyAt)
      if (this.options.groupReply === 'mention' && !directlyAddressed) return undefined
      if (!directlyAddressed) {
        groupReservationAt = this.groupRate.reserve(key, now, recentMessages)
        if (groupReservationAt === undefined) return undefined
      }
    }
    const sender = event.sender ?? {}
    const card = typeof sender.card === 'string' && sender.card.length > 0 ? sender.card : undefined
    const nickname = typeof sender.nickname === 'string' && sender.nickname.length > 0 ? sender.nickname : undefined
    const senderName = card ?? nickname ?? senderId

    return {
      key,
      kind,
      targetId,
      title: kind === 'group' ? groupId : senderName,
      messageId: event.message_id === undefined ? '' : String(event.message_id),
      senderName,
      senderId,
      text: rendered.text,
      segments: segmentsOf(event),
      directlyAddressed,
      ...(groupReservationAt !== undefined ? { groupReservationAt } : {}),
    }
  }

  /** Handle one accepted message. */
  private async handle(job: InboundJob): Promise<void> {
    let replied = false
    try {
      const receivedAt = this.now()
      const sessionId = await this.ensureSession(job)
      if (sessionId === undefined) return

      const agent = await this.resolveAgent(sessionId)
      if (agent === undefined || this.closed) return

      this.buffers.delete(sessionId)
      const prompt = buildPrompt(job, this.options.timeZone, receivedAt)
      const settled = this.waitForTurn(sessionId)
      agent.followup({
        id: randomUUID(),
        role: 'user',
        content: [{ type: 'text', text: prompt }],
        source: { kind: 'user', rpcId: `dsh-ai-love:${job.messageId || randomUUID()}` },
      })
      const reason = await settled
      if (reason !== 'completed') {
        this.logger.warn(`dsh-ai-love: turn of ${job.key} ended with "${reason}", no reply is sent`)
        return
      }
      const text = this.takeReply(sessionId)
      if (text.length === 0) {
        this.logger.warn(`dsh-ai-love: turn of ${job.key} produced no text, no reply is sent`)
        return
      }
      await this.reply(job, text)
      if (job.kind === 'group') this.recordGroupReply(job)
      replied = true
    } finally {
      if (!replied) this.groupRate.release(job.key, job.groupReservationAt)
    }
  }

  /** Read the configured test clock, or the system clock. */
  private now(): number {
    return this.options.now?.() ?? Date.now()
  }

  /** Persist one successful group reply for the next cooldown decision. */
  private recordGroupReply(job: InboundJob): void {
    const now = this.now()
    this.groupRate.recordReply(job.key, job.groupReservationAt, now)
    const record = this.store.current.chats[job.key]
    if (record !== undefined) {
      recordChat(this.store.current, job.key, { ...record, lastGroupReplyAt: now })
      void this.store.flush()
    }
  }

  /** Find or create the session of one chat. */
  private async ensureSession(job: InboundJob): Promise<string | undefined> {
    const state = this.store.current
    const record = state.chats[job.key]
    const controller = requireService<SessionControllerService>(this.ctx, 'sessionController')

    const candidate = record?.sessionId ?? `qq-${job.kind}-${job.targetId}`
    const found = await controller.resolveAgent(candidate)
    if (!('error' in found) && found.agent !== undefined) {
      if (record?.sessionId !== candidate) {
        recordChat(state, job.key, {
          sessionId: candidate,
          kind: job.kind,
          targetId: job.targetId,
          title: job.title,
          updatedAt: Date.now(),
        })
        void this.store.flush()
      }
      return candidate
    }

    const created = await controller.create({ sessionId: candidate, cwd: this.options.workspaceDir })
    recordChat(state, job.key, {
      sessionId: created.sessionId,
      kind: job.kind,
      targetId: job.targetId,
      title: job.title,
      updatedAt: Date.now(),
    })
    void this.store.flush()
    if (created.sessionId !== candidate) {
      this.logger.info(`dsh-ai-love: chat ${job.key} uses new session ${created.sessionId}`)
    }
    return created.sessionId
  }

  /** Resolve the live agent of one session and apply the permission preset once. */
  private async resolveAgent(sessionId: string): Promise<AgentLike | undefined> {
    const cached = this.resolved.get(sessionId)
    if (cached !== undefined && !this.disposed.has(sessionId)) return cached

    const controller = requireService<SessionControllerService>(this.ctx, 'sessionController')
    const found = await controller.resolveAgent(sessionId)
    if ('error' in found) {
      this.logger.warn(`dsh-ai-love: cannot resolve session ${sessionId}: ${found.error.message ?? found.error.code ?? 'unknown'}`)
      return undefined
    }
    const agent = found.agent
    this.resolved.set(sessionId, agent)
    this.applyPreset(agent)
    return agent
  }

  /** Apply the permission preset so that no approval prompt waits for an answer. */
  private applyPreset(agent: AgentLike): void {
    const presets = optionalService<{ set(session: unknown, name: string): void }>(this.ctx, 'permissionPresets')
    if (presets === undefined) return
    try {
      presets.set((agent as unknown as { session: unknown }).session, this.options.permissionPreset)
    } catch (error) {
      this.logger.warn(`dsh-ai-love: cannot set permission preset "${this.options.permissionPreset}": ${(error as Error).message}`)
    }
  }

  /** Record one session event and settle a waiting turn. */
  private observe(session: SessionLike, event: SessionEventLike): void {
    const sessionId = typeof session.id === 'string' ? session.id : ''
    if (sessionId.length === 0) return
    if (event.type === 'assistant/message') {
      const data = event.data as { turn?: number; interrupted?: boolean } | undefined
      if (data === undefined || data.interrupted === true) return
      const turn = typeof data.turn === 'number' ? data.turn : -1
      if (turn < 0) return
      const text = assistantText(event.data)
      if (text.length === 0) return
      const buffer = this.buffers.get(sessionId) ?? []
      const existing = buffer.find(entry => entry.turn === turn)
      if (existing === undefined) buffer.push({ turn, text })
      else existing.text = text
      this.buffers.set(sessionId, buffer)
      return
    }
    if (event.type === 'turn/end') {
      const data = event.data as { turn?: number; reason?: { kind?: string } } | undefined
      const kind = data?.reason?.kind ?? 'unknown'
      const waiter = this.waiters.get(sessionId)
      if (waiter !== undefined) {
        this.waiters.delete(sessionId)
        waiter(kind)
      }
    }
  }

  /** Wait for the next turn end of one session. */
  private waitForTurn(sessionId: string): Promise<string> {
    return new Promise<string>(resolve => {
      const timer = setTimeout(() => {
        if (this.waiters.get(sessionId) === settle) this.waiters.delete(sessionId)
        resolve('timeout')
      }, this.options.turnTimeoutMs)
      timer.unref?.()
      const settle = (reason: string): void => {
        clearTimeout(timer)
        resolve(reason)
      }
      this.waiters.set(sessionId, settle)
    })
  }

  /** Take the reply text of the settled turn. */
  private takeReply(sessionId: string): string {
    const buffer = this.buffers.get(sessionId) ?? []
    this.buffers.delete(sessionId)
    const latest = buffer[buffer.length - 1]
    if (latest === undefined) return ''
    return toPlainChatText(latest.text)
  }

  /** Send one reply to the chat of one job. */
  private async reply(job: InboundJob, text: string): Promise<void> {
    const parts = splitReply(text, this.options.maxReplyChars)
    for (const [index, part] of parts.entries()) {
      const quote = index === 0 && job.messageId.length > 0 && job.kind === 'group' ? job.messageId : undefined
      const segments = buildOutbound(part, quote)
      if (job.kind === 'group') {
        const result = await this.client.sendGroup(job.targetId, segments)
        const messageId = sentMessageId(result)
        if (messageId !== undefined) rememberSentMessage(this.sentGroupMessageIds, messageId)
      } else {
        await this.client.sendPrivate(job.targetId, segments)
      }
    }
  }

  /** Forget the cached agent of one session. */
  forget(sessionId: string): void {
    this.resolved.delete(sessionId)
    this.disposed.add(sessionId)
    this.buffers.delete(sessionId)
  }

  /** The state that the bridge works on. */
  get state(): BridgeState {
    return this.store.current
  }
}
