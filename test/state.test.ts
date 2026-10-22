/**
 * Tests of the durable bridge state.
 *
 * @module dsh-luoyu/test/state.test
 */

import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { chatKey, emptyState, loadState, markSeen, recordChat, saveState, StateStore, statePath } from '../src/state.ts'
import type { PluginLogger } from '../src/context.ts'

const silent: PluginLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
}

/** Create a temporary directory and remove it after the test. */
async function withTempDir(body: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-luoyu-state-'))
  try {
    await body(dir)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

test('builds a stable chat key from the kind and the target', () => {
  assert.equal(chatKey('private', '10001'), 'private:10001')
  assert.equal(chatKey('group', '782795932'), 'group:782795932')
})

test('returns the empty state before anything happens', () => {
  const state = emptyState()
  assert.equal(state.version, 1)
  assert.deepEqual(state.chats, {})
  assert.deepEqual(state.seenMessageIds, [])
})

test('reads the empty state when the file is absent', async () => {
  await withTempDir(async dir => {
    const state = await loadState(dir, silent)
    assert.deepEqual(state, emptyState())
  })
})

test('writes the state and reads it back', async () => {
  await withTempDir(async dir => {
    const state = emptyState()
    recordChat(state, 'group:1', {
      sessionId: 'qq-group-1',
      kind: 'group',
      targetId: '1',
      title: 'Friends',
      updatedAt: 1000,
      lastGroupReplyAt: 900,
    })
    markSeen(state, 'm-1')
    await saveState(dir, state)

    const loaded = await loadState(dir, silent)
    assert.equal(loaded.chats['group:1']?.sessionId, 'qq-group-1')
    assert.equal(loaded.chats['group:1']?.lastGroupReplyAt, 900)
    assert.deepEqual(loaded.seenMessageIds, ['m-1'])
  })
})

test('starts new chat sessions when the configured workspace changes', async () => {
  await withTempDir(async dir => {
    const store = new StateStore(dir, silent)
    await store.load()
    recordChat(store.current, 'group:1', {
      sessionId: 'old-session',
      kind: 'group',
      targetId: '1',
      title: 'Friends',
      updatedAt: 1,
    })
    assert.equal(await store.setWorkspaceDir('/workspace/one'), false)
    assert.equal(store.current.chats['group:1']?.sessionId, 'old-session')
    assert.equal(await store.setWorkspaceDir('/workspace/two'), true)
    assert.deepEqual(store.current.chats, {})
    await store.close()

    const loaded = await loadState(dir, silent)
    assert.equal(loaded.workspaceDir, '/workspace/two')
  })
})

test('writes the state file with owner-only permissions', async () => {
  await withTempDir(async dir => {
    await saveState(dir, emptyState())
    const { stat } = await import('node:fs/promises')
    const info = await stat(statePath(dir))
    assert.equal(info.mode & 0o777, 0o600)
  })
})

test('renames a corrupt state file aside and starts empty', async () => {
  await withTempDir(async dir => {
    await writeFile(statePath(dir), '{ not json', 'utf8')
    const state = await loadState(dir, silent)
    assert.deepEqual(state, emptyState())
    const aside = await readFile(`${statePath(dir)}.corrupt`, 'utf8')
    assert.equal(aside, '{ not json')
  })
})

test('drops a chat record that has no session identity', async () => {
  await withTempDir(async dir => {
    await writeFile(
      statePath(dir),
      JSON.stringify({ version: 1, chats: { 'group:1': { kind: 'group' }, 'private:2': { sessionId: 's', kind: 'private' } } }),
      'utf8',
    )
    const state = await loadState(dir, silent)
    assert.equal(state.chats['group:1'], undefined)
    assert.equal(state.chats['private:2']?.sessionId, 's')
  })
})

test('reports a message identity only once', () => {
  const state = emptyState()
  assert.equal(markSeen(state, 'm-1'), true)
  assert.equal(markSeen(state, 'm-1'), false)
  assert.deepEqual(state.seenMessageIds, ['m-1'])
})

test('keeps the newest message identities under the limit', () => {
  const state = emptyState()
  for (let index = 0; index < 2100; index += 1) markSeen(state, `m-${index}`)
  assert.equal(state.seenMessageIds.length, 2000)
  assert.equal(state.seenMessageIds[0], 'm-100')
  assert.equal(state.seenMessageIds[1999], 'm-2099')
})

test('the store writes a snapshot that later changes do not mutate', async () => {
  await withTempDir(async dir => {
    const store = new StateStore(dir, silent)
    await store.load()
    recordChat(store.current, 'private:1', {
      sessionId: 's-1',
      kind: 'private',
      targetId: '1',
      title: 'Ada',
      updatedAt: 1,
    })
    const first = store.flush()
    markSeen(store.current, 'm-late')
    await first
    await store.close()

    const loaded = await loadState(dir, silent)
    assert.equal(loaded.chats['private:1']?.sessionId, 's-1')
    assert.deepEqual(loaded.seenMessageIds, [])
  })
})
