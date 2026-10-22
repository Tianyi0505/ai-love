/**
 * OneBot 11 client.
 *
 * The client holds one WebSocket to NapCat for the inbound event stream and
 * calls the HTTP action endpoint for outbound messages. A dropped socket
 * reconnects with a bounded backoff. Every action call carries the access
 * token when one is configured.
 *
 * @module dsh-ai-love/onebot/client
 */

import WebSocket from 'ws'
import type { ActionResult, MessageEvent, MessageSegment, NoticeEvent } from './types.ts'
import type { PluginLogger } from '../context.ts'

/** Connection settings for one NapCat instance. */
export interface OneBotOptions {
  /** WebSocket URL of the event stream, for example `ws://127.0.0.1:3001`. */
  wsUrl: string
  /** HTTP base URL of the action endpoint, for example `http://127.0.0.1:3000`. */
  httpUrl: string
  /** Access token that NapCat requires, when it requires one. */
  accessToken?: string
  /** Timeout for one HTTP action call, in milliseconds. */
  actionTimeoutMs?: number
  /** Largest reconnect delay, in milliseconds. */
  maxReconnectDelayMs?: number
}

/** The listeners that the client calls. */
export interface OneBotListeners {
  /** Called for each inbound message event. */
  onMessage(event: MessageEvent): void
  /** Called for each inbound notice event. */
  onNotice?(event: NoticeEvent): void
  /** Called after each successful connection. */
  onConnect?(): void
  /** Called after the socket closes. */
  onDisconnect?(reason: string): void
}

/** The error that one rejected action call raises. */
export class OneBotActionError extends Error {
  readonly action: string
  readonly retcode: number | undefined

  constructor(action: string, message: string, retcode?: number) {
    super(message)
    this.name = 'OneBotActionError'
    this.action = action
    this.retcode = retcode
  }
}

/** Join the base URL and the action name. */
function actionUrl(base: string, action: string): string {
  return `${base.replace(/\/+$/, '')}/${action}`
}

/**
 * A OneBot 11 client with a self-healing event socket.
 *
 * The client is inert until `start()` runs and inert again after `stop()`
 * resolves. A reconnect attempt never outlives `stop()`.
 */
export class OneBotClient {
  private readonly options: Required<Pick<OneBotOptions, 'actionTimeoutMs' | 'maxReconnectDelayMs'>> & OneBotOptions
  private readonly listeners: OneBotListeners
  private readonly logger: PluginLogger
  private socket: WebSocket | undefined
  private running = false
  private reconnectAttempt = 0
  private reconnectTimer: NodeJS.Timeout | undefined
  private stopped: Promise<void> = Promise.resolve()
  private stopResolve: (() => void) | undefined

  constructor(options: OneBotOptions, listeners: OneBotListeners, logger: PluginLogger) {
    this.options = {
      actionTimeoutMs: 15_000,
      maxReconnectDelayMs: 30_000,
      ...options,
    }
    this.listeners = listeners
    this.logger = logger
  }

  /** True while the event socket is open. */
  get connected(): boolean {
    return this.socket !== undefined && this.socket.readyState === WebSocket.OPEN
  }

  /** Open the event socket and keep it open until `stop()`. */
  start(): void {
    if (this.running) return
    this.running = true
    this.stopped = new Promise<void>(resolve => {
      this.stopResolve = resolve
    })
    this.connect()
  }

  /**
   * Close the event socket and cancel a pending reconnect.
   *
   * @returns a promise that resolves after the socket closes.
   */
  async stop(): Promise<void> {
    if (!this.running) return
    this.running = false
    if (this.reconnectTimer !== undefined) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = undefined
    }
    const socket = this.socket
    this.socket = undefined
    if (socket !== undefined) {
      // A socket that is still connecting reports a close as an error event.
      // Keep one listener so that the report does not reach the process.
      socket.on('error', () => {})
      socket.removeAllListeners('message')
      socket.removeAllListeners('open')
      socket.removeAllListeners('close')
      if (socket.readyState === WebSocket.OPEN) socket.close()
      else if (socket.readyState === WebSocket.CONNECTING) socket.terminate()
    }
    this.stopResolve?.()
    this.stopResolve = undefined
    await this.stopped
  }

  /** Open one socket and attach the event handlers. */
  private connect(): void {
    if (!this.running) return
    const headers: Record<string, string> = {}
    if (this.options.accessToken !== undefined && this.options.accessToken.length > 0) {
      headers.Authorization = `Bearer ${this.options.accessToken}`
    }
    const socket = new WebSocket(this.options.wsUrl, { headers })
    this.socket = socket

    socket.on('open', () => {
      this.reconnectAttempt = 0
      this.logger.info(`dsh-ai-love: OneBot event socket open at ${this.options.wsUrl}`)
      this.listeners.onConnect?.()
    })

    socket.on('message', (data: WebSocket.RawData) => {
      this.dispatch(data.toString())
    })

    socket.on('error', (error: Error) => {
      this.logger.warn(`dsh-ai-love: OneBot event socket error: ${error.message}`)
    })

    socket.on('close', (code: number, reason: Buffer) => {
      if (this.socket === socket) this.socket = undefined
      const detail = reason.toString() || `code ${code}`
      this.listeners.onDisconnect?.(detail)
      if (!this.running) {
        this.stopResolve?.()
        return
      }
      this.scheduleReconnect()
    })
  }

  /** Schedule the next reconnect attempt with a capped exponential delay. */
  private scheduleReconnect(): void {
    if (this.reconnectTimer !== undefined) return
    const attempt = this.reconnectAttempt
    this.reconnectAttempt = Math.min(attempt + 1, 10)
    const delay = Math.min(500 * 2 ** attempt, this.options.maxReconnectDelayMs)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined
      this.connect()
    }, delay)
    this.reconnectTimer.unref?.()
  }

  /** Route one raw frame to the matching listener. */
  private dispatch(raw: string): void {
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      this.logger.warn('dsh-ai-love: OneBot event socket received a frame that is not JSON')
      return
    }
    if (typeof parsed !== 'object' || parsed === null) return
    const frame = parsed as { post_type?: string }
    if (frame.post_type === 'message') {
      this.listeners.onMessage(frame as MessageEvent)
      return
    }
    if (frame.post_type === 'notice' || frame.post_type === 'request' || frame.post_type === 'meta_event') {
      this.listeners.onNotice?.(frame as NoticeEvent)
    }
  }

  /**
   * Call one HTTP action.
   *
   * @param action - The action name, for example `send_group_msg`.
   * @param payload - The action body.
   * @param signal - Optional abort signal.
   * @returns the action data.
   * @throws OneBotActionError when the transport fails or NapCat reports an error.
   */
  async call<T = unknown>(action: string, payload: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(new Error('timeout')), this.options.actionTimeoutMs)
    timer.unref?.()
    const abort = (): void => controller.abort(signal?.reason)
    signal?.addEventListener('abort', abort, { once: true })
    const headers: Record<string, string> = { 'content-type': 'application/json' }
    if (this.options.accessToken !== undefined && this.options.accessToken.length > 0) {
      headers.Authorization = `Bearer ${this.options.accessToken}`
    }
    try {
      const response = await fetch(actionUrl(this.options.httpUrl, action), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      const text = await response.text()
      if (!response.ok) {
        throw new OneBotActionError(action, `NapCat returned HTTP ${response.status} for ${action}: ${text.slice(0, 200)}`)
      }
      let body: ActionResult<T>
      try {
        body = JSON.parse(text) as ActionResult<T>
      } catch {
        throw new OneBotActionError(action, `NapCat returned a body that is not JSON for ${action}`)
      }
      if (body.status !== undefined && body.status !== 'ok') {
        throw new OneBotActionError(
          action,
          body.message ?? body.wording ?? `NapCat rejected ${action}`,
          body.retcode,
        )
      }
      if (body.retcode !== undefined && body.retcode !== 0) {
        throw new OneBotActionError(action, body.message ?? body.wording ?? `NapCat rejected ${action}`, body.retcode)
      }
      return body.data as T
    } catch (error) {
      if (error instanceof OneBotActionError) throw error
      throw new OneBotActionError(action, `NapCat action ${action} failed: ${(error as Error).message}`)
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
    }
  }

  /**
   * Send one private message.
   *
   * @param userId - The recipient QQ number.
   * @param message - The outbound segments.
   * @param signal - Optional abort signal.
   */
  async sendPrivate(userId: string, message: readonly MessageSegment[], signal?: AbortSignal): Promise<void> {
    await this.call('send_private_msg', { user_id: Number(userId), message }, signal)
  }

  /**
   * Send one group message.
   *
   * @param groupId - The target group number.
   * @param message - The outbound segments.
   * @param signal - Optional abort signal.
   */
  async sendGroup(groupId: string, message: readonly MessageSegment[], signal?: AbortSignal): Promise<{ message_id?: number | string } | undefined> {
    return this.call<{ message_id?: number | string }>('send_group_msg', { group_id: Number(groupId), message }, signal)
  }

  /** Read one message by identity, including a quoted message. */
  async getMessage(messageId: string): Promise<MessageEvent | undefined> {
    return this.call<MessageEvent>('get_msg', { message_id: Number(messageId) })
  }

  /** Read the messages of one forwarded chat. */
  async getForward(forwardId: string): Promise<{ messages?: MessageEvent[] } | undefined> {
    return this.call<{ messages?: MessageEvent[] }>('get_forward_msg', { id: forwardId })
  }

  /** Read the members of one group. */
  async getGroupMembers(groupId: string): Promise<Array<Record<string, unknown>>> {
    const data = await this.call<Array<Record<string, unknown>>>('get_group_member_list', {
      group_id: Number(groupId),
      no_cache: false,
    })
    return Array.isArray(data) ? data : []
  }

  /** Read the friend list. */
  async getFriends(): Promise<Array<Record<string, unknown>>> {
    const data = await this.call<Array<Record<string, unknown>>>('get_friend_list', {})
    return Array.isArray(data) ? data : []
  }

  /** Read the account that the client is logged in as. */
  async getLoginInfo(): Promise<{ user_id?: number; nickname?: string } | undefined> {
    return this.call<{ user_id?: number; nickname?: string }>('get_login_info', {})
  }
}
