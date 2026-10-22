/**
 * Tests of the chat bridge helpers.
 *
 * @module dsh-ai-love/test/bridge.test
 */

import assert from 'node:assert/strict'
import test from 'node:test'
import { buildPrompt, splitReply } from '../src/bridge.ts'

test('keeps a short reply in one part', () => {
  assert.deepEqual(splitReply('hello', 100), ['hello'])
})

test('splits a long reply at the last newline that fits', () => {
  const text = `${'a'.repeat(40)}\n${'b'.repeat(40)}`
  const parts = splitReply(text, 50)
  assert.deepEqual(parts, ['a'.repeat(40), 'b'.repeat(40)])
})

test('splits a long reply without a newline at the limit', () => {
  const parts = splitReply('c'.repeat(120), 50)
  assert.equal(parts.length, 3)
  assert.equal(parts.join('').length, 120)
})

test('splits a Chinese reply at a full stop', () => {
  const sentence = `${'字'.repeat(30)}。`
  const parts = splitReply(sentence.repeat(4), 80)
  assert.ok(parts.length > 1)
  for (const part of parts) assert.ok(part.length <= 80)
})

test('returns one part when the limit is not positive', () => {
  assert.deepEqual(splitReply('hello', 0), ['hello'])
})

test('builds a group prompt with the group number and the sender', () => {
  const text = buildPrompt(
    {
      key: 'group:782795932',
      kind: 'group',
      targetId: '782795932',
      title: '782795932',
      messageId: 'm-1',
      senderName: 'Ada',
      senderId: '10001',
      text: 'hello',
      segments: [],
    },
    'Asia/Shanghai',
    Date.UTC(2026, 9, 22, 2, 30),
  )
  assert.match(text, /group chat "782795932" \(group 782795932\)/)
  assert.match(text, /Asia\/Shanghai/)
  assert.match(text, /^Ada \(QQ 10001\): hello$/m)
  assert.match(text, /2026-10-22 10:30/)
})

test('builds a private prompt with the other QQ number', () => {
  const text = buildPrompt(
    {
      key: 'private:10001',
      kind: 'private',
      targetId: '10001',
      title: 'Ada',
      messageId: 'm-2',
      senderName: 'Ada',
      senderId: '10001',
      text: 'hi',
      segments: [],
    },
    'Asia/Shanghai',
    Date.UTC(2026, 9, 22, 2, 30),
  )
  assert.match(text, /private chat with Ada \(QQ 10001\)/)
  assert.match(text, /^Ada \(QQ 10001\): hi$/m)
})
