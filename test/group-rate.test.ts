/** Tests of the group reply cadence. */

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  GROUP_ACTIVITY_WINDOW_MS,
  GroupReplyGate,
  groupCooldownMs,
  normalizeGroupReplyMode,
  rememberSentMessage,
  sentMessageId,
} from '../src/group-rate.ts'

test('uses the original quadratic cooldown range', () => {
  assert.equal(groupCooldownMs(2), 300_000)
  assert.equal(groupCooldownMs(5), 142_500)
  assert.equal(groupCooldownMs(8), 90_000)
  assert.equal(groupCooldownMs(100), 90_000)
})

test('requires two group messages in the original three-minute window', () => {
  const gate = new GroupReplyGate()
  assert.equal(gate.observe('group:1', 1000), 1)
  assert.equal(gate.reserve('group:1', 1000, 1), undefined)
  assert.equal(gate.observe('group:1', 2000), 2)
  assert.equal(gate.reserve('group:1', 2000, 2), 2000)
  assert.equal(gate.observe('group:1', 2000 + GROUP_ACTIVITY_WINDOW_MS + 1), 1)
})

test('allows only one in-flight proactive reservation per group', () => {
  const gate = new GroupReplyGate()
  gate.observe('group:1', 1000)
  const messages = gate.observe('group:1', 1001)
  assert.equal(gate.reserve('group:1', 1001, messages), 1001)
  assert.equal(gate.reserve('group:1', 1002, messages + 1), undefined)
  gate.release('group:1', 1001)
  assert.equal(gate.reserve('group:1', 1002, messages + 1), 1002)
})

test('applies cooldown after a successful group reply', () => {
  const gate = new GroupReplyGate()
  gate.observe('group:1', 1000)
  const messages = gate.observe('group:1', 1001)
  const reservation = gate.reserve('group:1', 1001, messages)
  assert.equal(reservation, 1001)
  gate.recordReply('group:1', reservation, 1002)
  assert.equal(gate.reserve('group:1', 1003, messages + 1), undefined)
})

test('normalizes the retired all-message mode to balanced', () => {
  assert.equal(normalizeGroupReplyMode('all'), 'balanced')
  assert.equal(normalizeGroupReplyMode('mention'), 'mention')
})

test('reads and bounds the identities of sent group replies', () => {
  assert.equal(sentMessageId({ message_id: 42 }), '42')
  assert.equal(sentMessageId({ message_id: '42' }), '42')
  assert.equal(sentMessageId({ message_id: Number.NaN }), undefined)
  const ids = new Set<string>()
  for (let index = 0; index < 2001; index += 1) rememberSentMessage(ids, String(index))
  assert.equal(ids.size, 2000)
  assert.equal(ids.has('0'), false)
})
