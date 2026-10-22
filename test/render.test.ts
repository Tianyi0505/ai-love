/**
 * Tests of the inbound segment renderer.
 *
 * @module dsh-ai-love/test/render.test
 */

import assert from 'node:assert/strict'
import test from 'node:test'
import { buildOutbound, renderInbound, toPlainChatText } from '../src/onebot/render.ts'
import type { MessageSegment } from '../src/onebot/types.ts'

test('renders text and joins consecutive text segments', () => {
  const segments: MessageSegment[] = [
    { type: 'text', data: { text: 'hello ' } },
    { type: 'text', data: { text: 'world' } },
  ]
  const result = renderInbound(segments)
  assert.equal(result.text, 'hello world')
  assert.equal(result.empty, false)
})

test('renders an at segment as a name and records the target', () => {
  const result = renderInbound([
    { type: 'at', data: { qq: '12345', name: 'Ada' } },
    { type: 'text', data: { text: ' look at this' } },
  ])
  assert.equal(result.text, '@Ada look at this')
  assert.deepEqual(result.mentionedUserIds, ['12345'])
})

test('records the quote target and keeps it out of the transcript', () => {
  const result = renderInbound([
    { type: 'reply', data: { id: '777' } },
    { type: 'text', data: { text: 'agreed' } },
  ])
  assert.equal(result.text, 'agreed')
  assert.equal(result.replyToMessageId, '777')
})

test('counts media and renders a label for each kind', () => {
  const result = renderInbound([
    { type: 'image', data: { file: 'a.jpg' } },
    { type: 'record', data: { file: 'b.amr' } },
    { type: 'file', data: { name: 'notes.pdf' } },
    { type: 'forward', data: { id: 'f1' } },
  ])
  assert.equal(result.imageCount, 1)
  assert.equal(result.voiceCount, 1)
  assert.equal(result.fileCount, 1)
  assert.equal(result.forwardCount, 1)
  assert.equal(result.text, '[image] [voice] [file:notes.pdf] [forwarded chat]')
})

test('renders an emoji segment with its identity', () => {
  const result = renderInbound([{ type: 'face', data: { id: '14' } }])
  assert.equal(result.text, '[emoji:14]')
})

test('reports an empty result for an empty segment list', () => {
  const result = renderInbound([])
  assert.equal(result.empty, true)
  assert.equal(result.text, '')
})

test('reports an empty result when the segments carry no renderable content', () => {
  const result = renderInbound([{ type: 'reply', data: { id: '1' } }])
  assert.equal(result.empty, true)
})

test('builds a quote segment before the text', () => {
  const segments = buildOutbound('hi', '42')
  assert.deepEqual(segments, [
    { type: 'reply', data: { id: '42' } },
    { type: 'text', data: { text: 'hi' } },
  ])
})

test('omits the quote segment when the identity is empty', () => {
  const segments = buildOutbound('hi', '')
  assert.deepEqual(segments, [{ type: 'text', data: { text: 'hi' } }])
})

test('flattens the Markdown that a chat platform does not render', () => {
  const text = toPlainChatText('## Title\n\n**bold** and `code`\n\n- one\n- two')
  assert.equal(text, 'Title\n\nbold and code\n\n- one\n- two')
})

test('turns a Markdown link into text with the URL in parentheses', () => {
  const text = toPlainChatText('see [the docs](https://example.com/a)')
  assert.equal(text, 'see the docs (https://example.com/a)')
})

test('keeps a bullet asterisk that is not emphasis', () => {
  const text = toPlainChatText('a * b * c')
  assert.equal(text, 'a * b * c')
})
