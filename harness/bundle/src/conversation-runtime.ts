import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent, AgentHandle } from '@deepseek-ai/dsh-agent'
import type { UserMessage } from '@deepseek-ai/dsh-llm'
import type { SessionId as DshSessionId } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-system-prompt'
import type { ConversationAddress } from './markdown-memory.ts'
import { MarkdownMemory, conversationSessionId } from './markdown-memory.ts'

export interface ConversationInput extends ConversationAddress {
  senderId: string
  senderName?: string
  messageId?: string
  text: string
}

export interface ConversationOutput {
  sessionId: string
  text: string
  memoryDirectory: string
}

interface RuntimeOptions {
  agentPreset: string
}

function promptFor(input: ConversationInput): string {
  return [
    `[platform=${input.platform}] [chat=${input.chatType}:${input.chatId}]`,
    `[sender=${input.senderName || input.senderId} (${input.senderId})]`,
    input.text,
  ].join('\n')
}

function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== 'object' || Object.isFrozen(value)) return value
  for (const child of Object.values(value)) deepFreeze(child)
  return Object.freeze(value)
}

function userMessage(text: string): UserMessage {
  return deepFreeze({
    id: randomUUID() as UserMessage['id'],
    role: 'user' as const,
    content: [{ type: 'text' as const, text }],
    source: { kind: 'user' as const },
  }) as UserMessage
}

function assistantText(agent: Agent, afterEventCount: number): string {
  const messages = agent.session.snapshotEvents().slice(afterEventCount).flatMap((event) => {
    if (event.type !== 'assistant/message') return []
    const text = event.data.message.content.flatMap(part => part.type === 'text' ? [part.text] : []).join('')
    return text.trim() ? [text.trim()] : []
  })
  const result = messages.at(-1)
  if (!result) throw new Error(`DSH session ${agent.id} completed without a text response`)
  return result
}

export class ConversationRuntime {
  private readonly handles = new Map<string, AgentHandle>()
  private readonly queues = new Map<string, Promise<void>>()
  private readonly ctx: Context
  private readonly memory: MarkdownMemory
  private readonly options: RuntimeOptions

  constructor(ctx: Context, memory: MarkdownMemory, options: RuntimeOptions) {
    this.ctx = ctx
    this.memory = memory
    this.options = options
  }

  dispatch(input: ConversationInput): Promise<ConversationOutput> {
    const sessionId = conversationSessionId(input)
    const previous = this.queues.get(sessionId) ?? Promise.resolve()
    const result = previous.catch(() => undefined).then(() => this.dispatchSerial(input))
    const tail = result.then(() => undefined, () => undefined)
    this.queues.set(sessionId, tail)
    void tail.finally(() => {
      if (this.queues.get(sessionId) === tail) this.queues.delete(sessionId)
    })
    return result
  }

  private async dispatchSerial(input: ConversationInput): Promise<ConversationOutput> {
    const memory = await this.memory.ensureConversation(input)
    const handle = await this.agentFor(memory.sessionId, input.aiId ?? 'default', {
      sharedDirectory: memory.sharedDirectory,
      identityDirectory: memory.identityDirectory,
      conversationDirectory: memory.conversationDirectory,
    })
    const before = handle.agent.session.snapshotEvents().length
    handle.agent.followup(userMessage(promptFor(input)))
    await handle.agent.whenIdle()
    return {
      sessionId: memory.sessionId,
      text: assistantText(handle.agent, before),
      memoryDirectory: memory.conversationDirectory,
    }
  }

  private async agentFor(
    rawSessionId: string,
    aiId: string,
    directories: { sharedDirectory: string; identityDirectory: string; conversationDirectory: string },
  ): Promise<AgentHandle> {
    const cached = this.handles.get(rawSessionId)
    if (cached) return cached
    const sessionId = rawSessionId as DshSessionId
    const setup = (agentCtx: Context): void => {
      agentCtx.systemPrompt.section({
        name: 'ai-love:conversation',
        order: -10_000,
        text: [
          `You are the digital identity ${aiId} speaking in a social conversation.`,
          'Treat the latest user message as social chat, not as a software-engineering task.',
          'Use the Markdown files under the following directories as durable memory:',
          `- shared across all chats: ${directories.sharedDirectory}`,
          `- shared by this identity: ${directories.identityDirectory}`,
          `- private to this chat: ${directories.conversationDirectory}`,
          'Read relevant Markdown before answering. Update Markdown only for durable facts; never store secrets or transient chatter.',
          'Reply with only the message that should be sent back to the chat.',
        ].join('\n'),
      })
    }
    let handle: AgentHandle
    try {
      handle = await this.ctx.agents.resume({ resumeSessionId: sessionId, setup })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      if (!/not found|persistence is not configured/iu.test(message)) throw error
      handle = await this.ctx.agents.create({
        sessionId,
        meta: {
          cwd: this.memory.workspaceDirectory,
          agentPreset: this.options.agentPreset,
        },
        setup,
      })
    }
    this.handles.set(rawSessionId, handle)
    return handle
  }

  async dispose(): Promise<void> {
    await Promise.allSettled([...this.handles.values()].map(handle => handle.dispose()))
    this.handles.clear()
    this.queues.clear()
  }
}
