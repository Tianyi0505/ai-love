/**
 * Group reply cadence.
 *
 * The original gateway used a relationship score. This bridge has no
 * relationship service, so recent group activity supplies a local score while
 * the original 90–300 second curve stays intact.
 *
 * @module dsh-ai-love/group-rate
 */

/** The original group join window. */
export const GROUP_ACTIVITY_WINDOW_MS = 180_000
/** The original minimum group message count before proactive participation. */
export const GROUP_MIN_MESSAGES = 2
/** The original minimum group reply cooldown. */
export const GROUP_MIN_COOLDOWN_MS = 90_000
/** The original maximum group reply cooldown. */
export const GROUP_MAX_COOLDOWN_MS = 300_000
/** The number of messages above the minimum that reaches the highest activity score. */
export const GROUP_ACTIVITY_SCORE_RANGE = 6

/** Derive a cooldown from recent activity using the original quadratic curve. */
export function groupCooldownMs(recentMessages: number): number {
  const score = Math.max(0, Math.min(1, (recentMessages - GROUP_MIN_MESSAGES) / GROUP_ACTIVITY_SCORE_RANGE))
  const span = GROUP_MAX_COOLDOWN_MS - GROUP_MIN_COOLDOWN_MS
  return Math.round(GROUP_MIN_COOLDOWN_MS + span * (1 - score) ** 2)
}

/** Reserve a group turn only when the group is active and the cooldown has passed. */
export class GroupReplyGate {
  private readonly activity = new Map<string, number[]>()
  private readonly lastReplies = new Map<string, number>()
  private readonly reservations = new Map<string, number>()

  /** Record an incoming message and return the number in the active window. */
  observe(key: string, now: number, lastReplyAt?: number): number {
    if (!this.lastReplies.has(key) && lastReplyAt !== undefined) this.lastReplies.set(key, lastReplyAt)
    const cutoff = now - GROUP_ACTIVITY_WINDOW_MS
    const recent = (this.activity.get(key) ?? []).filter(time => time >= cutoff && time <= now)
    recent.push(now)
    this.activity.set(key, recent)
    return recent.length
  }

  /** Reserve one proactive turn. Return its timestamp, or `undefined` when gated. */
  reserve(key: string, now: number, recentMessages: number): number | undefined {
    if (recentMessages < GROUP_MIN_MESSAGES) return undefined
    const previous = Math.max(
      this.lastReplies.get(key) ?? Number.NEGATIVE_INFINITY,
      this.reservations.get(key) ?? Number.NEGATIVE_INFINITY,
    )
    if (now - previous < groupCooldownMs(recentMessages)) return undefined
    this.reservations.set(key, now)
    return now
  }

  /** Record a successful group reply and clear its reservation. */
  recordReply(key: string, reservationAt: number | undefined, now: number): void {
    this.release(key, reservationAt)
    this.lastReplies.set(key, now)
  }

  /** Release a reservation when the turn does not send a reply. */
  release(key: string, reservationAt: number | undefined): void {
    if (reservationAt !== undefined && this.reservations.get(key) === reservationAt) {
      this.reservations.delete(key)
    }
  }
}

/** Sent OneBot message identity, returned by NapCat after a group reply. */
export function sentMessageId(result: unknown): string | undefined {
  if (typeof result !== 'object' || result === null) return undefined
  const id = (result as { message_id?: unknown }).message_id
  if (typeof id === 'string' && id.length > 0) return id
  if (typeof id === 'number' && Number.isFinite(id)) return String(id)
  return undefined
}

/** Keep the in-memory quote identity set bounded. */
export function rememberSentMessage(ids: Set<string>, id: string): void {
  ids.add(id)
  if (ids.size > 2000) {
    const oldest = ids.values().next().value as string | undefined
    if (oldest !== undefined) ids.delete(oldest)
  }
}

/** Recognize the retired all-message mode as the balanced policy. */
export function normalizeGroupReplyMode(value: 'mention' | 'balanced' | 'all'): 'mention' | 'balanced' {
  return value === 'mention' ? 'mention' : 'balanced'
}
