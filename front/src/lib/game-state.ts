/**
 * Pure functions for deriving game UI state from server responses.
 * Extracted from undercover.$gameId.tsx for testability.
 */

export type UndercoverPhase = "role_reveal" | "describing" | "playing" | "round_over" | "mr_white_guessing" | "game_over"

export interface DerivePhaseInput {
  winner: string | null | undefined
  turn_phase: string | null | undefined
  turn_number: number
  my_role: string | null | undefined
  roleRevealed: boolean
  /** The server's `round_resolved`: the votes were counted and someone left the table. */
  round_resolved?: boolean | null
}

/**
 * Derives the current UI phase from server state.
 *
 * Rules:
 * - If there's a winner → game_over
 * - If an eliminated Mr. White owes his guess → mr_white_guessing
 * - If turn_phase is "describing" → show "describing" (unless turn 1 + not revealed + not spectator → role_reveal)
 * - If the round is resolved → round_over (the turn stays in phase "voting" on the
 *   server until the host starts the next round, so without this the page kept
 *   showing an open vote that nobody could cast and never offered the next round)
 * - If turn_number > 0 (voting phase) → "playing"
 * - Otherwise (pre-game) → spectators see "describing", players see "role_reveal"
 */
export function deriveUndercoverPhase(input: DerivePhaseInput): UndercoverPhase {
  const { winner, turn_phase, turn_number, my_role, roleRevealed, round_resolved } = input
  const isSpectator = my_role === "spectator"

  if (winner) return "game_over"

  if (turn_phase === "mr_white_guessing") return "mr_white_guessing"

  if (turn_phase === "describing") {
    return roleRevealed || isSpectator || turn_number > 1 ? "describing" : "role_reveal"
  }

  if (round_resolved) return "round_over"

  if (turn_number > 0) return "playing"

  return isSpectator ? "describing" : "role_reveal"
}

export interface ServerPlayer {
  user_id: string
  username: string
  is_alive: boolean
  is_mayor?: boolean
}

export interface DerivePlayersInput {
  players: ServerPlayer[]
}

/**
 * Maps server player format to UI player format.
 */
export function derivePlayerList(players: ServerPlayer[]) {
  return players.map((p) => ({
    id: p.user_id,
    username: p.username,
    is_alive: p.is_alive,
    is_mayor: p.is_mayor,
  }))
}

/**
 * Extracts voted player IDs from the server votes object.
 */
export function deriveVotedPlayers(votes: Record<string, string> | null | undefined): string[] {
  return votes ? Object.keys(votes) : []
}
