/**
 * Structural view of the DeepSeek Harness plugin context.
 *
 * The plugin runs inside the Harness process. The Harness supplies every
 * service at run time, so this module declares only the members the plugin
 * uses. A local declaration keeps the package free of a run-time dependency on
 * the Harness packages and keeps the version gate simple.
 *
 * @module dsh-luoyu/context
 */

/** A log record sink. The Harness logger implements this interface. */
export interface PluginLogger {
  debug(...args: unknown[]): void
  info(...args: unknown[]): void
  warn(...args: unknown[]): void
  error(...args: unknown[]): void
}

/** One HTTP request that reaches a registered route. */
export interface WebRequest {
  method?: string
  url?: string
  headers: Record<string, string | string[] | undefined>
  on(event: 'data', listener: (chunk: unknown) => void): unknown
  on(event: 'end', listener: () => void): unknown
  on(event: 'error', listener: (error: Error) => void): unknown
}

/** One HTTP response that a route owns until it ends. */
export interface WebResponse {
  statusCode: number
  setHeader(name: string, value: string): void
  end(body?: string | Uint8Array): void
}

/** A route that the Harness web server exposes. */
export interface WebRoute {
  kind: 'exact' | 'prefix'
  path: string
  handler: (request: WebRequest, response: WebResponse) => void | Promise<void>
}

/** The Harness web server service. */
export interface WebServerService {
  register(route: WebRoute): () => void
  getOrigin(): string
}

/** The durable record of one committed session event. */
export interface SessionEventLike {
  type: string
  seq: number
  time: number
  data: unknown
}

/** The durable session log that the plugin observes. */
export interface SessionLike {
  readonly id: string
  readonly seq: number
  snapshotEvents(fromSeq?: number, toSeqExclusive?: number): readonly SessionEventLike[]
}

/** The result of a successful session-agent resolution. */
export interface ResolvedAgent {
  agent: AgentLike
}

/** The result of a failed session-agent resolution. */
export interface ResolveAgentFailure {
  error: { code?: string; message?: string }
}

/** One running agent that owns a session. */
export interface AgentLike {
  readonly id: string
  readonly session: SessionLike
  followup(message: unknown): void
}

/** Request body for `sessionController.create`. */
export interface SessionCreateRequest {
  workspaceId?: string
  cwd?: string
  sessionId?: string
  agentPreset?: string
}

/** Response body for `sessionController.create`. */
export interface SessionCreateValue {
  sessionId: string
  agentPreset?: string
}

/** One part of a prompt that the plugin sends to a session. */
export type PromptContentPart =
  | { type: 'text'; text: string }
  | { type: 'image'; mediaType: string; data: string; name?: string }

/** Request body for `sessionController.prompt`. */
export interface SessionPromptRequest {
  requestId: string
  sessionId: string
  mode: 'queue' | 'steer'
  content: readonly PromptContentPart[]
  clientTimeZone?: string
}

/** The subset of the Harness session controller that the plugin calls. */
export interface SessionControllerService {
  create(request: SessionCreateRequest): Promise<SessionCreateValue>
  resolveAgent(sessionId: string): Promise<ResolvedAgent | ResolveAgentFailure>
  prompt(request: SessionPromptRequest, signal?: AbortSignal): Promise<unknown>
}

/** One profile-owned plugin configuration entry. */
export interface ConfigEntryLike {
  readonly options: { readonly id: string; readonly config?: Record<string, unknown> }
}

/** The profile configuration editor supplied by the Harness. */
export interface ConfigEditorService {
  entries(): ConfigEntryLike[]
  edit(
    entry: ConfigEntryLike,
    change: (current: Record<string, unknown>, inherited: Record<string, unknown>) => Record<string, unknown>,
  ): Promise<void>
}

/** The Harness context that the plugin receives. */
export interface PluginContext {
  readonly logger: PluginLogger
  get(name: string): unknown
  inject(names: readonly string[], callback: (context: PluginContext) => void): void
  effect(execute: () => void | (() => void), label?: string): void
  on(name: string, listener: (...args: never[]) => void, options?: { global?: boolean }): () => void
}

/** Read a service from the context and fail when it is absent. */
export function requireService<T>(ctx: PluginContext, name: string): T {
  const service = ctx.get(name)
  if (service === undefined || service === null) {
    throw new Error(`dsh-luoyu requires the "${name}" service`)
  }
  return service as T
}

/** Read a service from the context and return undefined when it is absent. */
export function optionalService<T>(ctx: PluginContext, name: string): T | undefined {
  const service = ctx.get(name)
  return (service ?? undefined) as T | undefined
}
