import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-agent'
import { ConversationRuntime } from './conversation-runtime.ts'
import { HttpIngress } from './http-ingress.ts'
import { MarkdownMemory } from './markdown-memory.ts'

export const name = 'ai-love'

export interface Config {
  workspaceDirectory?: string
  memoryDirectory?: string
  agentPreset?: string
  ingressHost?: string
  ingressPort?: number
  ingressToken?: string
}

function portFrom(config: Config): number {
  const raw = config.ingressPort ?? Number(process.env.AILOVE_INGRESS_PORT ?? 8090)
  if (!Number.isSafeInteger(raw) || raw < 0 || raw > 65_535) {
    throw new Error(`ingressPort must be an integer from 0 to 65535, got ${String(raw)}`)
  }
  return raw
}

export async function apply(ctx: Context, config: Config = {}): Promise<void> {
  const workspaceDirectory = config.workspaceDirectory ?? process.env.AILOVE_WORKSPACE_DIRECTORY ?? process.cwd()
  const memory = new MarkdownMemory(
    workspaceDirectory,
    config.memoryDirectory ?? process.env.AILOVE_MEMORY_DIRECTORY ?? '.ai-love/memory',
  )
  await memory.initialize()

  ctx.inject(['agents'], (agentCtx) => {
    agentCtx.effect(async () => {
      const runtime = new ConversationRuntime(agentCtx, memory, {
        agentPreset: config.agentPreset ?? process.env.AILOVE_DSH_AGENT_PRESET ?? 'standard',
      })
      const ingress = new HttpIngress(runtime, {
        host: config.ingressHost ?? process.env.AILOVE_INGRESS_HOST ?? '127.0.0.1',
        port: portFrom(config),
        token: config.ingressToken ?? process.env.AILOVE_INGRESS_TOKEN,
      })
      await ingress.start()
      ctx.logger.info(`ai-love: workspace=${memory.workspaceDirectory} memory=${memory.memoryDirectory}`)
      return async () => {
        await ingress.stop()
        await runtime.dispose()
      }
    }, 'ai-love.runtime')
  })
}
