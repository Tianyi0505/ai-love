/**
 * Render inbound OneBot segments as text and build outbound segments.
 *
 * The model reads a plain-text transcript. This module flattens the segment
 * list into that transcript and collects the facts the bridge needs: the
 * mention targets, the quoted message identity, and the media attachments.
 *
 * @module dsh-luoyu/onebot/render
 */

import { segmentString, type MessageSegment } from './types.ts'

/** Facts that the bridge reads from one inbound message. */
export interface RenderedMessage {
  /** The plain-text transcript of the message body. */
  text: string
  /** User identifiers that the message mentions. */
  mentionedUserIds: string[]
  /** Identity of the quoted message, when the message quotes another message. */
  replyToMessageId: string | undefined
  /** Number of image segments. */
  imageCount: number
  /** Number of voice segments. */
  voiceCount: number
  /** Number of file segments. */
  fileCount: number
  /** Number of forwarded-chat segments. */
  forwardCount: number
  /** True when the message body carries no text and no media. */
  empty: boolean
}

/** Build the empty result. */
function emptyResult(): RenderedMessage {
  return {
    text: '',
    mentionedUserIds: [],
    replyToMessageId: undefined,
    imageCount: 0,
    voiceCount: 0,
    fileCount: 0,
    forwardCount: 0,
    empty: true,
  }
}

/** Render one media or control segment as a bracketed label. */
function label(segment: MessageSegment): string {
  const name = segmentString(segment, 'name') || segmentString(segment, 'file')
  switch (segment.type) {
    case 'face': {
      const id = segmentString(segment, 'id')
      return `[emoji:${id}]`
    }
    case 'mface': {
      const summary = segmentString(segment, 'summary') || segmentString(segment, 'emoji_id')
      return `[sticker:${summary}]`
    }
    case 'image':
      return '[image]'
    case 'record':
      return '[voice]'
    case 'video':
      return '[video]'
    case 'file':
      return name.length > 0 ? `[file:${name}]` : '[file]'
    case 'forward':
      return '[forwarded chat]'
    case 'json':
    case 'xml':
      return '[card]'
    case 'poke':
      return '[poke]'
    case 'dice':
      return '[dice]'
    case 'rps':
      return '[rps]'
    case 'share':
      return '[link]'
    case 'contact':
      return '[contact card]'
    case 'location':
      return '[location]'
    case 'music':
      return '[music]'
    case 'node':
      return '[forwarded message]'
    default:
      return `[${segment.type}]`
  }
}

/** Read the display name of one mention target. */
function mentionName(segment: MessageSegment): string {
  const name = segmentString(segment, 'name')
  if (name.length > 0) return name
  const id = segmentString(segment, 'qq')
  return id.length > 0 ? id : 'someone'
}

/**
 * Flatten one inbound segment list into a transcript.
 *
 * Consecutive text segments join without a separator. Every other segment
 * renders as a bracketed label with a single space before it.
 *
 * @param segments - The inbound segment list.
 * @returns the transcript and the collected facts.
 */
export function renderInbound(segments: readonly MessageSegment[]): RenderedMessage {
  const result = emptyResult()
  const parts: string[] = []

  /** Append one part with a separator when the transcript already has text. */
  const append = (part: string): void => {
    parts.push(parts.length > 0 ? ` ${part}` : part)
    result.empty = false
  }

  for (const segment of segments) {
    switch (segment.type) {
      case 'text': {
        const text = segmentString(segment, 'text')
        if (text.length === 0) break
        parts.push(text)
        result.empty = false
        break
      }
      case 'at': {
        const target = segmentString(segment, 'qq')
        if (target.length > 0 && target !== 'all') result.mentionedUserIds.push(target)
        append(target === 'all' ? '@all' : `@${mentionName(segment)}`)
        break
      }
      case 'reply': {
        const id = segmentString(segment, 'id')
        if (id.length > 0 && result.replyToMessageId === undefined) result.replyToMessageId = id
        break
      }
      case 'image':
        result.imageCount += 1
        append(label(segment))
        break
      case 'record':
        result.voiceCount += 1
        append(label(segment))
        break
      case 'file':
        result.fileCount += 1
        append(label(segment))
        break
      case 'forward':
        result.forwardCount += 1
        append(label(segment))
        break
      default:
        append(label(segment))
        break
    }
  }

  result.text = parts.join('').trim()
  if (result.text.length === 0) result.empty = true
  return result
}

/** Build one text segment. */
export function textSegment(text: string): MessageSegment {
  return { type: 'text', data: { text } }
}

/** Build one quote segment. */
export function replySegment(messageId: string): MessageSegment {
  return { type: 'reply', data: { id: messageId } }
}

/**
 * Split one reply into outbound segments.
 *
 * OneBot renders a newline inside a single text segment as a line break, so a
 * plain reply needs one text segment only. A quote segment goes first when the
 * bridge replies to a specific message.
 *
 * @param text - The reply text.
 * @param quoteMessageId - Identity of the message to quote, when known.
 * @returns the outbound segment list.
 */
export function buildOutbound(text: string, quoteMessageId?: string): MessageSegment[] {
  const segments: MessageSegment[] = []
  if (quoteMessageId !== undefined && quoteMessageId.length > 0) segments.push(replySegment(quoteMessageId))
  if (text.length > 0) segments.push(textSegment(text))
  return segments
}

/**
 * Remove the markdown that a chat platform does not render.
 *
 * The model writes Markdown. QQ shows the source characters, so the bridge
 * flattens the common constructs to plain text before it sends a reply.
 *
 * @param text - The reply text from the model.
 * @returns the plain-text reply.
 */
export function toPlainChatText(text: string): string {
  let output = text
  output = output.replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, '')
  output = output.replace(/\*\*([^*]+)\*\*/g, '$1')
  output = output.replace(/__([^_]+)__/g, '$1')
  output = output.replace(/(^|[^*\w])\*([^\s*][^*\n]*?)\*(?!\*)/g, '$1$2')
  output = output.replace(/`{1,3}([^`]*)`{1,3}/g, '$1')
  output = output.replace(/^[ \t]*[-*+][ \t]+/gm, '- ')
  output = output.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '$1 ($2)')
  output = output.replace(/[ \t]+$/gm, '')
  output = output.replace(/\n{3,}/g, '\n\n')
  return output.trim()
}
