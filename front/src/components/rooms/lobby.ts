import { formatClock, type HalqaSeat } from "@/components/brand"

/**
 * The lobby's pure logic: who sits where on the ring, whether the table can start, and
 * what just happened (the quiet activity line). Kept apart from the page so it can be
 * tested without a router, a socket or a query client.
 */

export type GameType = "undercover" | "codenames" | "word_quiz" | "mcq_quiz"

export const GAME_TYPES: readonly GameType[] = ["undercover", "codenames", "word_quiz", "mcq_quiz"]

/** i18n key of each game's display name (DESIGN.md §10). */
export const GAME_NAME_KEY: Record<GameType, string> = {
  undercover: "games.undercover.name",
  codenames: "games.codenames.name",
  word_quiz: "games.wordQuiz.name",
  mcq_quiz: "games.mcqQuiz.name",
}

/** Seated players needed to start (backend MIN_PLAYERS_*). */
export const MIN_PLAYERS: Record<GameType, number> = { undercover: 3, codenames: 4, word_quiz: 1, mcq_quiz: 1 }

/** Seats a table can hold (backend MAX_PLAYERS_*); the quizzes have no ceiling. */
export const MAX_PLAYERS: Partial<Record<GameType, number>> = { undercover: 12, codenames: 10 }

/** The ring draws at most this many seats (Halqa's own limit). */
const RING_SEATS = 12

/** Names longer than this are clipped on the ring (the roster keeps them whole). */
const RING_NAME_MAX = 10

export function isGameType(value: unknown): value is GameType {
  return typeof value === "string" && (GAME_TYPES as readonly string[]).includes(value)
}

export interface LobbyMember {
  id: string
  username: string
  isHost: boolean
  isSpectator: boolean
  /** Lost the connection: the seat is kept through the grace period. */
  isAway: boolean
  /** Seconds left of that grace when the state was sent (server's rule; null while here). */
  awaySecondsLeft: number | null
}

interface RawPlayer {
  user_id?: string
  username?: string
  is_spectator?: boolean
  is_disconnected?: boolean
  away_seconds_left?: number | null
}

/** Room state players → members. The host is whoever owns the room right now. */
export function toMembers(players: unknown, ownerId: string): LobbyMember[] {
  if (!Array.isArray(players)) return []
  return (players as RawPlayer[]).map((p) => ({
    id: p.user_id ?? "",
    username: p.username ?? "",
    isHost: !!p.user_id && p.user_id === ownerId,
    isSpectator: !!p.is_spectator,
    isAway: !!p.is_disconnected,
    awaySecondsLeft: typeof p.away_seconds_left === "number" ? p.away_seconds_left : null,
  }))
}

/**
 * How long each away seat is still kept, counted down on this screen from the server's
 * `away_seconds_left` (whole seconds, at `receivedAt`, the moment the state arrived):
 * id → seconds left, never below 0. Seats without a countdown are absent.
 */
export function awayCountdown(members: LobbyMember[], receivedAt: number, now: number): Map<string, number> {
  const passed = Math.max(0, Math.floor((now - receivedAt) / 1000))
  const left = new Map<string, number>()
  for (const m of members) {
    if (m.isAway && m.awaySecondsLeft != null) left.set(m.id, Math.max(0, m.awaySecondsLeft - passed))
  }
  return left
}

/** "away · 9:58": the away label with the seat's countdown when there is one. */
export function awayLabel(away: string, secondsLeft: number | undefined): string {
  return secondsLeft == null ? away : `${away} · ${formatClock(secondsLeft)}`
}

export function ringName(name: string): string {
  const chars = Array.from(name)
  return chars.length > RING_NAME_MAX ? `${chars.slice(0, RING_NAME_MAX - 1).join("")}…` : name
}

export interface SeatLabels {
  you: string
  host: string
  youHost: string
  away: string
}

export interface Seating {
  /** Host first (the ṣadr), then everyone else in the server's order. */
  seats: HalqaSeat[]
  /** Seated (non-spectator) members in the same order, for the roster. */
  seated: LobbyMember[]
  spectators: LobbyMember[]
  capacity: number
  quorum: number
}

/**
 * The order in which members were first seen, newcomers appended. The server lists a
 * room's links in no fixed order (a reconnect can move a player), so the ring keeps
 * this order instead: seats never jump, and a newcomer sits after the last arrival.
 */
export function stableOrder(order: string[], members: LobbyMember[]): string[] {
  const present = new Set(members.map((m) => m.id))
  const kept = order.filter((id) => present.has(id))
  for (const m of members) if (!kept.includes(m.id)) kept.push(m.id)
  return kept
}

/**
 * Members → ring seats. Spectators are named under the ring, never seated (sketch D).
 * The ring shows a few open seats after the last player (at least six seats in all),
 * never more than the game holds or than the ring can draw. `order` (from stableOrder)
 * fixes the seating; without it the server's order is used. `awayLeft` (awayCountdown)
 * puts each away seat's countdown under its name ("away · 9:58").
 */
export function seatLobby(
  members: LobbyMember[],
  gameType: GameType,
  myId: string | undefined,
  labels: SeatLabels,
  order?: string[],
  awayLeft?: Map<string, number>,
): Seating {
  const rank = (m: LobbyMember) => (order ? order.indexOf(m.id) : 0)
  const seatedAll = members.filter((m) => !m.isSpectator).sort((a, b) => rank(a) - rank(b))
  const host = seatedAll.find((m) => m.isHost)
  const seated = host ? [host, ...seatedAll.filter((m) => m !== host)] : seatedAll
  const seats: HalqaSeat[] = seated.map((m) => {
    const me = m.id === myId
    const sub = m.isHost
      ? me
        ? labels.youHost
        : labels.host
      : m.isAway
        ? awayLabel(labels.away, awayLeft?.get(m.id))
        : me
          ? labels.you
          : undefined
    return {
      id: m.id,
      name: ringName(m.username),
      sub,
      state: m.isHost ? "host" : m.isAway ? "away" : "in",
      me,
    }
  })
  const ceiling = Math.min(MAX_PLAYERS[gameType] ?? RING_SEATS, RING_SEATS)
  const capacity = Math.min(RING_SEATS, Math.max(seats.length, Math.min(ceiling, Math.max(seats.length + 3, 6))))
  return {
    seats,
    seated,
    spectators: members.filter((m) => m.isSpectator),
    capacity,
    quorum: MIN_PLAYERS[gameType],
  }
}

export type TableState = { kind: "ready" } | { kind: "short"; missing: number } | { kind: "over"; max: number }

/** Can this many seated players start this game? */
export function tableState(seatedCount: number, gameType: GameType): TableState {
  const min = MIN_PLAYERS[gameType]
  if (seatedCount < min) return { kind: "short", missing: min - seatedCount }
  const max = MAX_PLAYERS[gameType]
  if (max !== undefined && seatedCount > max) return { kind: "over", max }
  return { kind: "ready" }
}

export type LobbyEventKind = "joined" | "watching" | "left" | "away" | "back" | "host"

export interface LobbyEvent {
  kind: LobbyEventKind
  name: string
}

/**
 * What changed between two rosters, oldest first. Events about the viewer are left out
 * (they know), except a change of host. An empty `prev` is the first roster seen: it is
 * the baseline, not a wave of arrivals.
 */
export function rosterEvents(prev: LobbyMember[], next: LobbyMember[], myId: string | undefined): LobbyEvent[] {
  if (prev.length === 0) return []
  const before = new Map(prev.map((m) => [m.id, m]))
  const after = new Map(next.map((m) => [m.id, m]))
  const events: LobbyEvent[] = []
  for (const m of next) {
    if (m.id === myId) continue
    const was = before.get(m.id)
    if (!was) events.push({ kind: m.isSpectator ? "watching" : "joined", name: m.username })
    // a spectator's connection is shown nowhere: its flicker is not news
    else if (m.isSpectator) continue
    else if (!was.isAway && m.isAway) events.push({ kind: "away", name: m.username })
    else if (was.isAway && !m.isAway) events.push({ kind: "back", name: m.username })
  }
  for (const m of prev) {
    if (m.id !== myId && !after.has(m.id)) events.push({ kind: "left", name: m.username })
  }
  const oldHost = prev.find((m) => m.isHost)
  const newHost = next.find((m) => m.isHost)
  if (newHost && oldHost && newHost.id !== oldHost.id) events.push({ kind: "host", name: newHost.username })
  return events
}
