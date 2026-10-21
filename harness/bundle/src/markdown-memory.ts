import { createHash } from 'node:crypto'
import { mkdir, realpath, writeFile } from 'node:fs/promises'
import { isAbsolute, join, relative, resolve } from 'node:path'

export type ChatType = 'group' | 'private'

export interface ConversationAddress {
  platform: string
  accountId: string
  chatType: ChatType
  chatId: string
  aiId?: string
}

export interface ConversationMemory {
  sessionId: string
  sharedDirectory: string
  identityDirectory: string
  conversationDirectory: string
}

function digest(value: string, length = 24): string {
  return createHash('sha256').update(value).digest('hex').slice(0, length)
}

function cleanLabel(value: string): string {
  const label = value.normalize('NFKC').replace(/[^\p{L}\p{N}._-]+/gu, '-').replace(/^-+|-+$/gu, '').slice(0, 40)
  return label || 'default'
}

function markdownValue(value: string): string {
  return value.replaceAll('`', '\\`').replace(/[\r\n]+/gu, ' ')
}

async function writeOnce(path: string, content: string): Promise<void> {
  try {
    await writeFile(path, content, { encoding: 'utf8', flag: 'wx' })
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error
  }
}

export function conversationSessionId(address: ConversationAddress): string {
  const key = [address.platform, address.accountId, address.chatType, address.chatId].join('\u001f')
  return `ai-love-${digest(key)}`
}

export class MarkdownMemory {
  readonly workspaceDirectory: string
  readonly memoryDirectory: string

  constructor(workspaceDirectory: string, memoryDirectory: string) {
    const workspace = resolve(workspaceDirectory)
    const memory = resolve(workspace, memoryDirectory)
    const location = relative(workspace, memory)
    if (location.startsWith('..') || isAbsolute(location)) {
      throw new Error('memoryDirectory must resolve inside workspaceDirectory')
    }
    this.workspaceDirectory = workspace
    this.memoryDirectory = memory
  }

  async initialize(): Promise<void> {
    await mkdir(this.workspaceDirectory, { recursive: true })
    const canonicalWorkspace = await realpath(this.workspaceDirectory)
    const sameWorkspace = process.platform === 'win32'
      ? canonicalWorkspace.toLocaleLowerCase('en-US') === this.workspaceDirectory.toLocaleLowerCase('en-US')
      : canonicalWorkspace === this.workspaceDirectory
    if (!sameWorkspace) {
      throw new Error(`workspaceDirectory must use its canonical path: ${canonicalWorkspace}`)
    }
    const shared = join(this.memoryDirectory, 'shared')
    await mkdir(shared, { recursive: true })
    await writeOnce(join(shared, 'README.md'), [
      '# Shared memory',
      '',
      'This directory contains durable facts that may be useful in more than one DSH conversation.',
      'Agents should keep entries concise, sourced, and safe to share across chats.',
      '',
    ].join('\n'))
  }

  async ensureConversation(address: ConversationAddress): Promise<ConversationMemory> {
    const sessionId = conversationSessionId(address)
    const identityName = `${cleanLabel(address.aiId ?? 'default')}-${digest(address.aiId ?? 'default', 10)}`
    const sharedDirectory = join(this.memoryDirectory, 'shared')
    const identityDirectory = join(this.memoryDirectory, 'identities', identityName)
    const conversationDirectory = join(this.memoryDirectory, 'conversations', sessionId)
    await Promise.all([
      mkdir(identityDirectory, { recursive: true }),
      mkdir(conversationDirectory, { recursive: true }),
    ])
    await Promise.all([
      writeOnce(join(identityDirectory, 'MEMORY.md'), `# Identity memory: ${markdownValue(address.aiId ?? 'default')}\n\n`),
      writeOnce(join(conversationDirectory, 'MEMORY.md'), [
        '# Conversation memory',
        '',
        `- DSH session: \`${sessionId}\``,
        `- Platform: \`${markdownValue(address.platform)}\``,
        `- Account: \`${markdownValue(address.accountId)}\``,
        `- Chat type: \`${address.chatType}\``,
        `- Chat: \`${markdownValue(address.chatId)}\``,
        '',
      ].join('\n')),
    ])
    return { sessionId, sharedDirectory, identityDirectory, conversationDirectory }
  }
}
