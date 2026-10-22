/**
 * Plugin entry point.
 *
 * The plugin wires four parts: the NapCat sidecar, the OneBot client, the chat
 * bridge, and the status page. The bridge is the only part that talks to the
 * Harness session controller.
 *
 * @module dsh-luoyu
 */

import { mkdir } from 'node:fs/promises'
import { dirname } from 'node:path'
import type { Config } from './config.ts'
import { defaultDataDir, resolveConfig } from './config.ts'
import { ChatBridge } from './bridge.ts'
import type { PluginContext, PluginLogger } from './context.ts'
import { NapCatSidecar } from './napcat.ts'
import { OneBotClient } from './onebot/client.ts'
import type { MessageEvent } from './onebot/types.ts'
import { StateStore } from './state.ts'
import { findWebServer, registerRoutes } from './web.ts'
import { scaffoldWorkspace } from './workspace.ts'

/** The plugin name that the loader reports. */
export const name = 'dsh-luoyu'

/**
 * The configuration schema.
 *
 * The loader reads this export to apply the defaults before it calls
 * {@link apply}. A plugin that omits the export receives the raw configuration
 * and no default.
 */
export { Config } from './config.ts'

/** Services that the plugin waits for. */
export const inject = ['sessionController', 'permissionPresets', 'sessions']

/** Resolve the data directory from the workspace setting. */
function dataDirOf(config: Config): string {
  const fallback = defaultDataDir()
  // The state lives next to the managed sidecar, not inside the workspace, so
  // that a workspace reset keeps the chat-to-session mapping.
  return config.napcatDir.length > 0 ? dirname(config.napcatDir) : fallback
}

/** Read the port from a URL, with the protocol default. */
function portOf(url: string, fallback: number): number {
  try {
    const parsed = new URL(url)
    if (parsed.port.length > 0) return Number(parsed.port)
    return parsed.protocol === 'wss:' || parsed.protocol === 'https:' ? 443 : 80
  } catch {
    return fallback
  }
}

/**
 * Start the plugin.
 *
 * @param ctx - the Harness plugin context.
 * @param input - the operator configuration.
 */
export async function apply(ctx: PluginContext, input?: Partial<Config>): Promise<void> {
  const config = resolveConfig(input)
  const logger: PluginLogger = ctx.logger
  const dataDir = dataDirOf(config)
  await mkdir(dataDir, { recursive: true })

  await scaffoldWorkspace(config.workspaceDir, config.persona, logger)

  const store = new StateStore(dataDir, logger)
  await store.load()
  if (await store.setWorkspaceDir(config.workspaceDir)) {
    logger.info('dsh-luoyu: the workspace changed; chats will start new sessions on their next message')
  }

  const sidecar = new NapCatSidecar(
    {
      napcatDir: config.napcatDir,
      version: config.napcatVersion,
      wsPort: portOf(config.wsUrl, 3001),
      httpPort: portOf(config.httpUrl, 3000),
      accessToken: config.accessToken,
      uin: config.uin,
      webuiPort: config.napcatWebuiPort,
      webuiToken: config.napcatWebuiToken,
      autoStart: config.autoStart,
    },
    logger,
  )

  const client = new OneBotClient(
    {
      wsUrl: config.wsUrl,
      httpUrl: config.httpUrl,
      ...(config.accessToken.length > 0 ? { accessToken: config.accessToken } : {}),
    },
    {
      onMessage: (event: MessageEvent) => {
        bridge.accept(event)
      },
      onConnect: () => {
        logger.info('dsh-luoyu: the OneBot event stream is connected')
      },
      onDisconnect: (reason: string) => {
        logger.warn(`dsh-luoyu: the OneBot event stream closed: ${reason}`)
      },
    },
    logger,
  )

  const bridge = new ChatBridge(
    ctx,
    client,
    store,
    {
      workspaceDir: config.workspaceDir,
      privateReply: config.privateReply,
      groupReply: config.groupReply,
      permissionPreset: config.permissionPreset,
      timeZone: config.timeZone,
      maxReplyChars: config.maxReplyChars,
      turnTimeoutMs: config.turnTimeoutMs,
      uin: config.uin,
    },
    logger,
  )

  bridge.start()
  client.start()

  ctx.effect(() => {
    const webServer = findWebServer(ctx)
    const disposeRoutes =
      webServer === undefined
        ? () => undefined
        : registerRoutes(ctx, webServer, sidecar, bridge, config.workspaceDir, config.uin, () => client.connected, logger, config)

    if (config.autoStart && config.napcatMode === 'managed') {
      void sidecar.start().catch((error: unknown) => {
        logger.warn(`dsh-luoyu: the managed NapCat sidecar did not start: ${(error as Error).message}`)
      })
    }

    return () => {
      disposeRoutes()
      void bridge.close()
      void client.stop()
      void sidecar.stop()
      void store.close()
    }
  }, 'dsh-luoyu lifecycle')

  logger.info(`dsh-luoyu: ready, workspace is ${config.workspaceDir}`)
}
