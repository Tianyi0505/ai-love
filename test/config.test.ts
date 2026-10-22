/**
 * Tests of the configuration defaults.
 *
 * @module dsh-luoyu/test/config.test
 */

import assert from 'node:assert/strict'
import { homedir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { Config, DEFAULT_PERSONA, defaultDataDir, defaultWorkspaceDir, resolveConfig, resolveDshHome } from '../src/config.ts'

/** Validate a partial configuration the way the Harness does. */
const parse = Config as unknown as (input: Record<string, unknown>) => ReturnType<typeof Config>

test('reads the Harness home from the environment', () => {
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = '/tmp/custom-home'
  try {
    assert.equal(resolveDshHome(), '/tmp/custom-home')
  } finally {
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
  }
})

test('falls back to the home directory when the variable is blank', () => {
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = '   '
  try {
    assert.equal(resolveDshHome(), join(homedir(), '.dsh'))
  } finally {
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
  }
})

test('uses the Luoyu integration path and the requested memory workspace', () => {
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = '/tmp/custom-home'
  try {
    assert.equal(defaultDataDir(), join('/tmp/custom-home', 'integrations', 'dsh-luoyu'))
    assert.equal(defaultWorkspaceDir(), '/workspace/memroy')
  } finally {
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
  }
})

test('accepts an empty configuration and fills every field', () => {
  const value = parse({})
  assert.equal(value.privateReply, true)
  assert.equal(value.groupReply, 'balanced')
  assert.equal(value.napcatMode, 'managed')
  assert.equal(value.wsUrl, 'ws://127.0.0.1:3001')
  assert.equal(value.httpUrl, 'http://127.0.0.1:3000')
  assert.equal(value.autoStart, true)
  assert.equal(value.permissionPreset, 'danger-full-access')
  assert.equal(value.timeZone, 'Asia/Shanghai')
  assert.equal(value.maxReplyChars, 1500)
  assert.equal(value.turnTimeoutMs, 600_000)
  assert.equal(value.napcatWebuiPort, 6099)
  assert.equal(value.napcatVersion, 'latest')
  assert.equal(value.persona, DEFAULT_PERSONA)
})

test('accepts the retired all mode and resolves it to balanced', () => {
  assert.equal(parse({ groupReply: 'all' }).groupReply, 'all')
  assert.equal(resolveConfig({ groupReply: 'all' }).groupReply, 'balanced')
})

test('rejects a group reply mode that the plugin does not know', () => {
  assert.throws(() => parse({ groupReply: 'sometimes' }))
})

test('rejects a negative reply limit', () => {
  assert.throws(() => parse({ maxReplyChars: -1 }))
})

test('the persona forbids the disclosure of credentials', () => {
  assert.match(DEFAULT_PERSONA, /Never reveal credentials/)
})
