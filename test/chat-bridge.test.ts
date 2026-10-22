/**
 * Tests of the chat bridge.
 *
 * The tests replace the Harness session controller and the OneBot client with
 * stand-ins. They cover the routing rules, the session mapping, the queue, and
 * the reply settlement.
 *
 * @module dsh-ai-love/test/chat-bridge.test
 */

import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { ChatBridge } from '../src/bridge.ts'
import type { GroupReplyMode } from '../src/config.ts'
import type { PluginContext, PluginLogger, SessionEventLike, SessionLike } from '../src/context.ts'
import type { OneBotClient } from '../src/onebot/client.ts'
import type { MessageEvent, MessageSegment } from '../src/onebot/types.ts'
import { StateStore } from '../src/state.ts'

const silent: PluginLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
}

/** One message that a stand-in agent received. */
interface Sent {
  id: string
  role: string
  content: Array<{ type: string; text: string }>
  source: { kind: string; rpcId?: string }
}

/** A stand-in agent that records the messages and can answer a turn. */
class FakeAgent {
  readonly id: string
  readonly session: SessionLike
  readonly sent: Sent[] = []

  constructor(sessionId: string) {
    this.id = sessionId
    this.session = { id: sessionId, seq: 0, snapshotEvents: () => [] }
  }

  followup(message: unknown): void {
    this.sent.push(message as Sent)
  }
}

/** A stand-in session controller. */
class FakeController {
  readonly agents = new Map<string, FakeAgent>()
  readonly created: string[] = []

  async create(request: { sessionId?: string }): Promise<{ sessionId: string }> {
    const sessionId = request.sessionId ?? `minted-${this.created.length}`
    this.created.push(sessionId)
    this.agents.set(sessionId, new FakeAgent(sessionId))
    return { sessionId }
  }

  async resolveAgent(sessionId: string): Promise<{ agent: FakeAgent } | { error: { code: string; message: string } }> {
    const agent = this.agents.get(sessionId)
    if (agent === undefined) return { error: { code: 'session/not-found', message: `no session ${sessionId}` } }
    return { agent }
  }

  async prompt(): Promise<unknown> {
    return { accepted: true }
  }
}

/** A stand-in OneBot client that records the replies. */
class FakeClient {
  readonly groups: Array<{ groupId: string; message: readonly MessageSegment[] }> = []
  readonly privates: Array<{ userId: string; message: readonly MessageSegment[] }> = []
  readonly connected = true

  async sendGroup(groupId: string, message: readonly MessageSegment[]): Promise<unknown> {
    this.groups.push({ groupId, message })
    return { message_id: `outbound-${this.groups.length}` }
  }

  async sendPrivate(userId: string, message: readonly MessageSegment[]): Promise<unknown> {
    this.privates.push({ userId, message })
    return { message_id: 2 }
  }
}

/** The listener that the bridge registers. */
type Listener = (session: SessionLike, event: SessionEventLike) => void

/** A stand-in plugin context. */
class FakeContext {
  readonly listeners: Listener[] = []
  readonly controller: FakeController

  constructor(controller: FakeController) {
    this.controller = controller
  }

  readonly logger = silent

  get(name: string): unknown {
    if (name === 'sessionController') return this.controller
    return undefined
  }

  inject(): void {
    // The bridge never injects.
  }

  effect(): void {
    // The bridge never registers an effect.
  }

  on(name: string, listener: Listener): () => void {
    if (name === 'session/event') this.listeners.push(listener)
    return () => {
      const index = this.listeners.indexOf(listener)
      if (index >= 0) this.listeners.splice(index, 1)
    }
  }

  /** Deliver one session event to every listener. */
  emit(session: SessionLike, event: SessionEventLike): void {
    for (const listener of this.listeners) listener(session, event)
  }
}

/** One group message that mentions the account. */
function groupEvent(patch: Partial<MessageEvent> = {}): MessageEvent {
  return {
    post_type: 'message',
    message_type: 'group',
    message_id: 101,
    group_id: 782795932,
    user_id: 10001,
    self_id: 3916750998,
    message: [
      { type: 'at', data: { qq: '3916750998' } },
      { type: 'text', data: { text: ' hello' } },
    ],
    sender: { user_id: 10001, nickname: 'Ada', card: 'Ada' },
    ...patch,
  }
}

/** One private message. */
function privateEvent(patch: Partial<MessageEvent> = {}): MessageEvent {
  return {
    post_type: 'message',
    message_type: 'private',
    message_id: 201,
    user_id: 10001,
    self_id: 3916750998,
    message: [{ type: 'text', data: { text: 'hi' } }],
    sender: { user_id: 10001, nickname: 'Ada' },
    ...patch,
  }
}

/** One reply from the model. */
function assistantEvent(turn: number, text: string): SessionEventLike {
  return {
    type: 'assistant/message',
    seq: 1,
    time: 1,
    data: { turn, step: 1, message: { content: [{ type: 'text', text }] } },
  }
}

/** The end of one turn. */
function turnEndEvent(turn: number, kind = 'completed'): SessionEventLike {
  return { type: 'turn/end', seq: 2, time: 2, data: { turn, reason: { kind } } }
}

/** Answer the open turn of one session, so the queue moves on. */
function answer(ctx: FakeContext, session: SessionLike, text: string, turn = 1, kind = 'completed'): void {
  if (text.length > 0) ctx.emit(session, assistantEvent(turn, text))
  ctx.emit(session, turnEndEvent(turn, kind))
}

/** Build a bridge over stand-in parts. */
async function setup(
  patch: { privateReply?: boolean; groupReply?: GroupReplyMode; uin?: string; now?: () => number } = {},
): Promise<{
  bridge: ChatBridge
  ctx: FakeContext
  client: FakeClient
  controller: FakeController
  store: StateStore
  dir: string
  close(): Promise<void>
}> {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-ai-love-bridge-'))
  const controller = new FakeController()
  const ctx = new FakeContext(controller)
  const client = new FakeClient()
  const store = new StateStore(dir, silent)
  await store.load()
  const bridge = new ChatBridge(
    ctx as unknown as PluginContext,
    client as unknown as OneBotClient,
    store,
    {
      workspaceDir: dir,
      privateReply: patch.privateReply ?? true,
      groupReply: patch.groupReply ?? 'balanced',
      now: patch.now,
      permissionPreset: 'danger-full-access',
      timeZone: 'Asia/Shanghai',
      maxReplyChars: 1500,
      turnTimeoutMs: 5000,
      uin: patch.uin ?? '3916750998',
    },
    silent,
  )
  bridge.start()
  return {
    bridge,
    ctx,
    client,
    controller,
    store,
    dir,
    close: async () => {
      await bridge.close()
      await store.close()
      await rm(dir, { recursive: true, force: true })
    },
  }
}

/** Wait until the condition holds. */
async function until(condition: () => boolean, timeoutMs = 3000): Promise<void> {
  const started = Date.now()
  while (!condition()) {
    if (Date.now() - started > timeoutMs) throw new Error('the condition did not hold in time')
    await new Promise(resolve => setTimeout(resolve, 5))
  }
}

test('ignores a message that the account sent itself', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent({ user_id: 3916750998 }))
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(parts.controller.created.length, 0)
  } finally {
    await parts.close()
  }
})

test('ignores a non-mention group message in mention-only mode', async () => {
  const parts = await setup({ groupReply: 'mention' })
  try {
    parts.bridge.accept(groupEvent({ message: [{ type: 'text', data: { text: 'hello' } }] }))
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(parts.controller.created.length, 0)
  } finally {
    await parts.close()
  }
})

test('answers a direct group mention even in mention-only mode', async () => {
  const parts = await setup({ groupReply: 'mention' })
  try {
    parts.bridge.accept(groupEvent())
    await until(() => parts.controller.created.length === 1)
    assert.equal(parts.controller.created[0], 'qq-group-782795932')
  } finally {
    await parts.close()
  }
})

test('accepts a balanced group message after two messages in the join window', async () => {
  let now = 1000
  const parts = await setup({ groupReply: 'balanced', now: () => now })
  try {
    const plain = [{ type: 'text', data: { text: 'hello' } }]
    parts.bridge.accept(groupEvent({ message_id: 102, message: plain }))
    await new Promise(resolve => setTimeout(resolve, 20))
    assert.equal(parts.controller.created.length, 0)

    now += 1
    parts.bridge.accept(groupEvent({ message_id: 103, message: plain }))
    await until(() => parts.controller.created.length === 1)
    assert.equal(parts.controller.created[0], 'qq-group-782795932')
  } finally {
    await parts.close()
  }
})

test('keeps a five-minute cooldown for low-activity groups', async () => {
  let now = 1000
  const parts = await setup({ groupReply: 'balanced', now: () => now })
  try {
    const plain = [{ type: 'text', data: { text: 'hello' } }]
    parts.bridge.accept(groupEvent({ message_id: 101, message: plain }))
    now += 1
    parts.bridge.accept(groupEvent({ message_id: 102, message: plain }))
    const agent = () => parts.controller.agents.get('qq-group-782795932')
    await until(() => (agent()?.sent.length ?? 0) === 1)
    const first = agent()
    assert.ok(first !== undefined)
    answer(parts.ctx, first.session, 'hello back')
    await until(() => parts.client.groups.length === 1)
    assert.equal(parts.bridge.state.chats['group:782795932']?.lastGroupReplyAt, now)

    now += 10
    parts.bridge.accept(groupEvent({ message_id: 103, message: plain }))
    now += 1
    parts.bridge.accept(groupEvent({ message_id: 104, message: plain }))
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(agent()?.sent.length, 1)

    now = 301_001
    parts.bridge.accept(groupEvent({ message_id: 105, message: plain }))
    now += 1
    parts.bridge.accept(groupEvent({ message_id: 106, message: plain }))
    await until(() => (agent()?.sent.length ?? 0) === 2)
  } finally {
    await parts.close()
  }
})

test('lets direct mentions bypass the balanced cooldown', async () => {
  let now = 1000
  const parts = await setup({ groupReply: 'balanced', now: () => now })
  try {
    parts.bridge.accept(groupEvent({ message_id: 201 }))
    const agent = () => parts.controller.agents.get('qq-group-782795932')
    await until(() => (agent()?.sent.length ?? 0) === 1)
    const first = agent()
    assert.ok(first !== undefined)
    answer(parts.ctx, first.session, 'hello back')
    await until(() => parts.client.groups.length === 1)

    now += 1
    parts.bridge.accept(groupEvent({ message_id: 202 }))
    await until(() => (agent()?.sent.length ?? 0) === 2)
  } finally {
    await parts.close()
  }
})

test('lets replies to the bot bypass mention-only mode', async () => {
  const parts = await setup({ groupReply: 'mention' })
  try {
    parts.bridge.accept(groupEvent({ message_id: 301 }))
    const agent = () => parts.controller.agents.get('qq-group-782795932')
    await until(() => (agent()?.sent.length ?? 0) === 1)
    const first = agent()
    assert.ok(first !== undefined)
    answer(parts.ctx, first.session, 'hello back')
    await until(() => parts.client.groups.length === 1)

    parts.bridge.accept(groupEvent({
      message_id: 302,
      message: [
        { type: 'reply', data: { id: 'outbound-1' } },
        { type: 'text', data: { text: 'thanks' } },
      ],
    }))
    await until(() => (agent()?.sent.length ?? 0) === 2)
  } finally {
    await parts.close()
  }
})

test('ignores a private message when private replies are off', async () => {
  const parts = await setup({ privateReply: false })
  try {
    parts.bridge.accept(privateEvent())
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(parts.controller.created.length, 0)
  } finally {
    await parts.close()
  }
})

test('ignores an empty message', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent({ message: [] }))
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(parts.controller.created.length, 0)
  } finally {
    await parts.close()
  }
})

test('ignores a repeated message identity', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.created.length === 1)
    parts.bridge.accept(privateEvent())
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(parts.controller.created.length, 1)
  } finally {
    await parts.close()
  }
})

test('creates one session per chat and reuses it', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    const agent = () => parts.controller.agents.get('qq-private-10001')
    await until(() => (agent()?.sent.length ?? 0) === 1)
    const first = agent()
    assert.ok(first !== undefined)
    answer(parts.ctx, first.session, 'one')
    await until(() => parts.client.privates.length === 1)
    parts.bridge.accept(privateEvent({ message_id: 202 }))
    await until(() => (agent()?.sent.length ?? 0) === 2)
    assert.equal(parts.controller.created.length, 1)
  } finally {
    await parts.close()
  }
})

test('creates a different session for a different chat', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    parts.bridge.accept(groupEvent())
    await until(() => parts.controller.created.length === 2)
    assert.deepEqual(parts.controller.created.sort(), ['qq-group-782795932', 'qq-private-10001'])
    for (const agent of parts.controller.agents.values()) answer(parts.ctx, agent.session, 'ok')
  } finally {
    await parts.close()
  }
})

test('sends the prompt text of one private message', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 1)
    const sent = parts.controller.agents.get('qq-private-10001')?.sent[0]
    assert.equal(sent?.role, 'user')
    assert.match(sent?.content[0]?.text ?? '', /private chat with Ada \(QQ 10001\)/)
    assert.match(sent?.content[0]?.text ?? '', /Ada \(QQ 10001\): hi/)
  } finally {
    await parts.close()
  }
})

test('answers the chat with the model text', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 1)
    const agent = parts.controller.agents.get('qq-private-10001')
    assert.ok(agent !== undefined)
    parts.ctx.emit(agent.session, assistantEvent(1, 'hello back'))
    parts.ctx.emit(agent.session, turnEndEvent(1))
    await until(() => parts.client.privates.length === 1)
    assert.equal(parts.client.privates[0]?.userId, '10001')
    assert.deepEqual(parts.client.privates[0]?.message, [{ type: 'text', data: { text: 'hello back' } }])
  } finally {
    await parts.close()
  }
})

test('quotes the first part of a group reply', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(groupEvent())
    await until(() => parts.controller.agents.get('qq-group-782795932')?.sent.length === 1)
    const agent = parts.controller.agents.get('qq-group-782795932')
    assert.ok(agent !== undefined)
    parts.ctx.emit(agent.session, assistantEvent(1, 'hi there'))
    parts.ctx.emit(agent.session, turnEndEvent(1))
    await until(() => parts.client.groups.length === 1)
    assert.equal(parts.client.groups[0]?.groupId, '782795932')
    assert.deepEqual(parts.client.groups[0]?.message, [
      { type: 'reply', data: { id: '101' } },
      { type: 'text', data: { text: 'hi there' } },
    ])
  } finally {
    await parts.close()
  }
})

test('does not answer when the turn ends with an error', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 1)
    const agent = parts.controller.agents.get('qq-private-10001')
    assert.ok(agent !== undefined)
    parts.ctx.emit(agent.session, assistantEvent(1, 'partial'))
    parts.ctx.emit(agent.session, turnEndEvent(1, 'error'))
    await new Promise(resolve => setTimeout(resolve, 40))
    assert.equal(parts.client.privates.length, 0)
  } finally {
    await parts.close()
  }
})

test('does not answer when the turn produced no text', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 1)
    const agent = parts.controller.agents.get('qq-private-10001')
    assert.ok(agent !== undefined)
    parts.ctx.emit(agent.session, turnEndEvent(1))
    await new Promise(resolve => setTimeout(resolve, 40))
    assert.equal(parts.client.privates.length, 0)
  } finally {
    await parts.close()
  }
})

test('ignores an interrupted assistant message', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 1)
    const agent = parts.controller.agents.get('qq-private-10001')
    assert.ok(agent !== undefined)
    parts.ctx.emit(agent.session, {
      type: 'assistant/message',
      seq: 1,
      time: 1,
      data: { turn: 1, step: 1, interrupted: true, message: { content: [{ type: 'text', text: 'cut' }] } },
    })
    parts.ctx.emit(agent.session, turnEndEvent(1))
    await new Promise(resolve => setTimeout(resolve, 40))
    assert.equal(parts.client.privates.length, 0)
  } finally {
    await parts.close()
  }
})

test('runs the messages of one chat in order', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent({ message_id: 301, message: [{ type: 'text', data: { text: 'first' } }] }))
    parts.bridge.accept(privateEvent({ message_id: 302, message: [{ type: 'text', data: { text: 'second' } }] }))
    const agent = () => parts.controller.agents.get('qq-private-10001')
    await until(() => (agent()?.sent.length ?? 0) >= 1)
    const first = agent()
    assert.ok(first !== undefined)
    answer(parts.ctx, first.session, 'one')
    await until(() => (agent()?.sent.length ?? 0) === 2)
    const texts = (agent()?.sent ?? []).map(entry => entry.content[0]?.text ?? '')
    assert.match(texts[0] ?? '', /first/)
    assert.match(texts[1] ?? '', /second/)
  } finally {
    await parts.close()
  }
})

test('records the chat mapping in the state file', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.bridge.state.chats['private:10001'] !== undefined)
    const record = parts.bridge.state.chats['private:10001']
    assert.equal(record?.sessionId, 'qq-private-10001')
    assert.equal(record?.kind, 'private')
    assert.equal(record?.targetId, '10001')
  } finally {
    await parts.close()
  }
})

test('forgets the cached agent of one session', async () => {
  const parts = await setup()
  try {
    parts.bridge.accept(privateEvent())
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 1)
    const before = parts.controller.agents.get('qq-private-10001')
    assert.ok(before !== undefined)
    answer(parts.ctx, before.session, 'one')
    await until(() => parts.client.privates.length === 1)
    parts.bridge.forget('qq-private-10001')
    parts.bridge.accept(privateEvent({ message_id: 999 }))
    await until(() => parts.controller.agents.get('qq-private-10001')?.sent.length === 2)
    assert.equal(parts.controller.created.length, 1)
  } finally {
    await parts.close()
  }
})

test('stops accepting after close', async () => {
  const parts = await setup()
  try {
    await parts.bridge.close()
    parts.bridge.accept(privateEvent())
    await new Promise(resolve => setTimeout(resolve, 30))
    assert.equal(parts.controller.created.length, 0)
  } finally {
    await parts.close()
  }
})
