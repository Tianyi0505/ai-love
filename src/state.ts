/**
 * Durable bridge state.
 *
 * The state maps one chat to one Harness session and records the messages that
 * the bridge already handled. The bridge writes the file after each change so
 * that a restart continues each conversation instead of starting a new one.
 *
 * @module dsh-ai-love/state
 */

import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { PluginLogger } from './context.ts'

/** One chat that the bridge knows. */
export interface ChatRecord {
  /** Harness session that holds the conversation. */
  sessionId: string
  /** Chat kind. */
  kind: 'private' | 'group'
  /** QQ number of the other person, or the group number. */
  targetId: string
  /** Display name of the chat. */
  title: string
  /** Unix epoch milliseconds of the last handled message. */
  updatedAt: number
}

/** The persisted bridge state. */
export interface BridgeState {
  version: 1
  /** Workspace used by the mapped sessions, when known. */
  workspaceDir?: string
  chats: Record<string, ChatRecord>
  seenMessageIds: string[]
}

/** Largest number of handled message identities that the state keeps. */
const SEEN_LIMIT = 2000

/** Build the key of one chat. */
export function chatKey(kind: 'private' | 'group', targetId: string): string {
  return `${kind}:${targetId}`
}

/** Build the empty state. */
export function emptyState(): BridgeState {
  return { version: 1, chats: {}, seenMessageIds: [] }
}

/** Path of the state file. */
export function statePath(dataDir: string): string {
  return join(dataDir, 'state.json')
}

/**
 * Read the state from disk.
 *
 * A missing or unreadable file yields the empty state. A corrupt file is
 * renamed aside so that the operator can inspect it.
 *
 * @param dataDir - directory that holds the state.
 * @param logger - log sink.
 * @returns the state.
 */
export async function loadState(dataDir: string, logger: PluginLogger): Promise<BridgeState> {
  const path = statePath(dataDir)
  let raw: string
  try {
    raw = await readFile(path, 'utf8')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      logger.warn(`dsh-ai-love: cannot read ${path}: ${(error as Error).message}`)
    }
    return emptyState()
  }
  try {
    const parsed = JSON.parse(raw) as Partial<BridgeState>
    const chats: Record<string, ChatRecord> = {}
    for (const [key, value] of Object.entries(parsed.chats ?? {})) {
      if (value === null || typeof value !== 'object') continue
      const record = value as Partial<ChatRecord>
      if (typeof record.sessionId !== 'string' || record.sessionId.length === 0) continue
      if (record.kind !== 'private' && record.kind !== 'group') continue
      chats[key] = {
        sessionId: record.sessionId,
        kind: record.kind,
        targetId: typeof record.targetId === 'string' ? record.targetId : '',
        title: typeof record.title === 'string' ? record.title : '',
        updatedAt: typeof record.updatedAt === 'number' ? record.updatedAt : 0,
      }
    }
    const seen = Array.isArray(parsed.seenMessageIds)
      ? parsed.seenMessageIds.filter((id): id is string => typeof id === 'string')
      : []
    return {
      version: 1,
      ...(typeof parsed.workspaceDir === 'string' ? { workspaceDir: parsed.workspaceDir } : {}),
      chats,
      seenMessageIds: seen.slice(-SEEN_LIMIT),
    }
  } catch (error) {
    logger.warn(`dsh-ai-love: ${path} is not valid JSON, starting empty: ${(error as Error).message}`)
    await rename(path, `${path}.corrupt`).catch(() => undefined)
    return emptyState()
  }
}

/**
 * Write the state to disk through a temporary file.
 *
 * @param dataDir - directory that holds the state.
 * @param state - the state to write.
 */
export async function saveState(dataDir: string, state: BridgeState): Promise<void> {
  const path = statePath(dataDir)
  await mkdir(dirname(path), { recursive: true })
  const body = `${JSON.stringify(state, undefined, 2)}\n`
  const temporary = `${path}.tmp`
  await writeFile(temporary, body, { mode: 0o600 })
  await rename(temporary, path)
}

/**
 * Record one handled message identity.
 *
 * @param state - the state to change.
 * @param messageId - identity of the handled message.
 * @returns true when the identity was new.
 */
export function markSeen(state: BridgeState, messageId: string): boolean {
  if (state.seenMessageIds.includes(messageId)) return false
  state.seenMessageIds.push(messageId)
  if (state.seenMessageIds.length > SEEN_LIMIT) {
    state.seenMessageIds.splice(0, state.seenMessageIds.length - SEEN_LIMIT)
  }
  return true
}

/**
 * Record one chat session.
 *
 * @param state - the state to change.
 * @param key - the chat key.
 * @param record - the chat record.
 */
export function recordChat(state: BridgeState, key: string, record: ChatRecord): void {
  state.chats[key] = record
}

/** Serialize the state writes of one process. */
export class StateStore {
  private readonly dataDir: string
  private readonly logger: PluginLogger
  private state: BridgeState = emptyState()
  private pending: Promise<void> = Promise.resolve()
  private loaded = false

  constructor(dataDir: string, logger: PluginLogger) {
    this.dataDir = dataDir
    this.logger = logger
  }

  /** Read the state once. */
  async load(): Promise<BridgeState> {
    if (!this.loaded) {
      this.state = await loadState(this.dataDir, this.logger)
      this.loaded = true
    }
    return this.state
  }

  /** The state in memory. Call `load()` first. */
  get current(): BridgeState {
    return this.state
  }

  /** Attach the chat mappings to the workspace that owns their sessions. */
  async setWorkspaceDir(workspaceDir: string): Promise<boolean> {
    if (this.state.workspaceDir === workspaceDir) return false
    const changed = this.state.workspaceDir !== undefined
    if (changed) this.state.chats = {}
    this.state.workspaceDir = workspaceDir
    await this.flush()
    return changed
  }

  /** Write the state after the current change. */
  flush(): Promise<void> {
    const snapshot: BridgeState = {
      version: 1,
      ...(this.state.workspaceDir !== undefined ? { workspaceDir: this.state.workspaceDir } : {}),
      chats: { ...this.state.chats },
      seenMessageIds: [...this.state.seenMessageIds],
    }
    this.pending = this.pending
      .then(() => saveState(this.dataDir, snapshot))
      .catch((error: unknown) => {
        this.logger.warn(`dsh-ai-love: cannot write the state: ${(error as Error).message}`)
      })
    return this.pending
  }

  /** Wait for every queued write. */
  async close(): Promise<void> {
    await this.pending
  }
}
