/**
 * Tests of the NapCat sidecar helpers.
 *
 * The tests cover the pure parts: the OneBot configuration, the display
 * detection, and the status defaults. They do not start NapCat.
 *
 * @module dsh-luoyu/test/napcat.test
 */

import assert from 'node:assert/strict'
import test from 'node:test'
import type { PluginLogger } from '../src/context.ts'
import { NapCatSidecar, SidecarDependencyError, buildOneBotConfig, detectQq, hasDisplay } from '../src/napcat.ts'
import type { SidecarOptions } from '../src/napcat.ts'

const silent: PluginLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
}

/** The options of one sidecar. */
function options(patch: Partial<SidecarOptions> = {}): SidecarOptions {
  return {
    napcatDir: '/tmp/napcat',
    version: 'latest',
    wsPort: 3001,
    httpPort: 3000,
    accessToken: 'token',
    uin: '3916750998',
    webuiPort: 6099,
    webuiToken: 'webui',
    autoStart: true,
    ...patch,
  }
}

test('opens one loopback HTTP server and one loopback WebSocket server', () => {
  const config = buildOneBotConfig(options())
  assert.equal(config.network.httpServers.length, 1)
  assert.equal(config.network.websocketServers.length, 1)
  assert.equal(config.network.httpServers[0]?.host, '127.0.0.1')
  assert.equal(config.network.websocketServers[0]?.host, '127.0.0.1')
  assert.equal(config.network.httpServers[0]?.port, 3000)
  assert.equal(config.network.websocketServers[0]?.port, 3001)
})

test('gives both servers the access token', () => {
  const config = buildOneBotConfig(options({ accessToken: 'shared-token' }))
  assert.equal(config.network.httpServers[0]?.token, 'shared-token')
  assert.equal(config.network.websocketServers[0]?.token, 'shared-token')
})

test('asks for array message bodies on both servers', () => {
  const config = buildOneBotConfig(options())
  assert.equal(config.network.httpServers[0]?.messagePostFormat, 'array')
  assert.equal(config.network.websocketServers[0]?.messagePostFormat, 'array')
})

test('does not report the messages of the account itself', () => {
  const config = buildOneBotConfig(options())
  assert.equal(config.network.websocketServers[0]?.reportSelfMessage, false)
})

test('leaves every unused network slot empty', () => {
  const config = buildOneBotConfig(options())
  assert.deepEqual(config.network.httpSseServers, [])
  assert.deepEqual(config.network.httpClients, [])
  assert.deepEqual(config.network.websocketClients, [])
  assert.deepEqual(config.network.plugins, [])
})

test('reports a display only when one of the variables is set', () => {
  const display = process.env.DISPLAY
  const wayland = process.env.WAYLAND_DISPLAY
  try {
    delete process.env.DISPLAY
    delete process.env.WAYLAND_DISPLAY
    assert.equal(hasDisplay(), false)
    process.env.DISPLAY = ':0'
    assert.equal(hasDisplay(), true)
    delete process.env.DISPLAY
    process.env.WAYLAND_DISPLAY = 'wayland-0'
    assert.equal(hasDisplay(), true)
  } finally {
    if (display === undefined) delete process.env.DISPLAY
    else process.env.DISPLAY = display
    if (wayland === undefined) delete process.env.WAYLAND_DISPLAY
    else process.env.WAYLAND_DISPLAY = wayland
  }
})

test('finds no QQ client on this host', async () => {
  const found = await detectQq()
  if (found !== undefined) assert.ok(found.startsWith('/'))
})

test('starts with an unknown phase and no installation', () => {
  const sidecar = new NapCatSidecar(options(), silent)
  assert.equal(sidecar.current.phase, 'unknown')
  assert.equal(sidecar.current.running, false)
  assert.equal(sidecar.current.installed, false)
  assert.deepEqual([...sidecar.log], [])
})

test('reports the installation facts without a start', async () => {
  const sidecar = new NapCatSidecar(options({ napcatDir: '/tmp/luoyu-missing-napcat' }), silent)
  const status = await sidecar.inspect()
  assert.equal(status.installed, false)
  assert.equal(status.phase, 'not-installed')
  assert.deepEqual(await sidecar.listInstallation(), [])
  assert.equal(await sidecar.installationSize(), 0)
})

test('raises a dependency error that names the missing piece', () => {
  const error = new SidecarDependencyError('needs-qq', 'install QQ first')
  assert.ok(error instanceof Error)
  assert.equal(error.name, 'SidecarDependencyError')
  assert.equal(error.phase, 'needs-qq')
  assert.equal(error.message, 'install QQ first')
})
