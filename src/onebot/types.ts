/**
 * OneBot 11 wire types.
 *
 * The plugin speaks OneBot 11 to NapCat over a WebSocket event stream and an
 * HTTP action endpoint. This module declares the parts of the protocol that
 * the plugin reads and writes.
 *
 * @module dsh-luoyu/onebot/types
 */

/** One message segment. */
export interface MessageSegment {
  type: string
  data: Record<string, unknown>
}

/** The sender of a message event. */
export interface MessageSender {
  user_id?: number
  nickname?: string
  card?: string
  role?: 'owner' | 'admin' | 'member' | string
}

/** One inbound message event. */
export interface MessageEvent {
  post_type?: string
  message_type?: 'private' | 'group' | string
  sub_type?: string
  message_id?: number
  message?: string | MessageSegment[]
  raw_message?: string
  user_id?: number
  group_id?: number
  self_id?: number
  time?: number
  sender?: MessageSender
}

/** One inbound notice event, such as a group recall. */
export interface NoticeEvent {
  post_type?: string
  notice_type?: string
  [key: string]: unknown
}

/** The reply body of one HTTP action. */
export interface ActionResult<T = unknown> {
  status?: string
  retcode?: number
  data?: T
  message?: string
  wording?: string
}

/** One group member record. */
export interface GroupMember {
  user_id: number
  nickname?: string
  card?: string
  role?: string
}

/** One friend record. */
export interface Friend {
  user_id: number
  nickname?: string
  remark?: string
}

/** Read a message event body as a segment list. */
export function segmentsOf(event: MessageEvent): MessageSegment[] {
  if (Array.isArray(event.message)) return event.message
  if (typeof event.message === 'string') {
    return event.message.length === 0 ? [] : [{ type: 'text', data: { text: event.message } }]
  }
  return []
}

/** Read one string field from a segment. */
export function segmentString(segment: MessageSegment, key: string): string {
  const value = segment.data[key]
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return ''
}
