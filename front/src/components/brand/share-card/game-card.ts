import type { NotebookGameWord } from "@/api/generated"
import { formatLasted, gameSeconds } from "@/components/games/shared/ColophonMeta"
import { type CardWord, type GameCardInput, MAX_CARD_WORDS } from "./model"

/**
 * What a finished game's colophon card says, in the player's language: from the
 * colophon's own fields (the same as `ColophonMeta`'s) and the notebook's read of the
 * game's words (public once it is over). Pure: `t` is passed in, so the strings are
 * tested on their own (`__tests__/inputs.test.ts`). The word of the day's card is
 * `daily-card.ts`, kept apart so a game's colophon never loads the day's code.
 */

export type T = (key: string, opts?: Record<string, unknown>) => string

/** The address a game card names (no scheme: it reads as text). */
export const SHARE_URL = "majlisna.app"

export type CardGame = "undercover" | "codenames" | "wordquiz" | "mcqquiz"

/** A finished game as its colophon names it: what `ColophonMeta` reads, plus which game. */
export interface ColophonShare {
  game: CardGame
  /** Who hosted it (`host_username`): "Yusuf’s majlis". */
  host?: string | null
  /** The game's own count, as the meta line shows it ("3 rounds", "9 clues"). */
  count?: string | null
  startedAt?: string | null
  endedAt?: string | null
}

/** The games' i18n keys (`games.*.name`, `home.fihrist.*.arabic`). */
const GAME_KEY: Record<CardGame, string> = { undercover: "undercover", codenames: "codenames", wordquiz: "wordQuiz", mcqquiz: "mcqQuiz" }

/** First-strong isolates: a name keeps its own direction inside a translated sentence (as ColophonMeta). */
const isolate = (text: string) => `⁨${text}⁩`

export const dirOf = (lang: string) => (lang.startsWith("ar") ? ("rtl" as const) : ("ltr" as const))

export function gameName(game: CardGame, t: T): string {
  return t(`games.${GAME_KEY[game]}.name`)
}

/** "Undercover · Yusuf’s majlis · 3 rounds · 21:40", as parts, from the same fields as `ColophonMeta`. */
export function gameMetaParts(share: ColophonShare, t: T): string[] {
  const parts = [gameName(share.game, t)]
  if (share.host) parts.push(t("game.colophon.majlis", { name: isolate(share.host) }))
  if (share.count) parts.push(share.count)
  const seconds = gameSeconds(share.startedAt, share.endedAt)
  if (seconds != null && seconds > 0) parts.push(formatLasted(seconds))
  return parts
}

/** A word as the card sets it: the vocalised Arabic, and the word as the interface shows it (not in the Arabic interface). */
function cardWord(w: NotebookGameWord, arabicUi: boolean): CardWord {
  const arabic = w.word_ar_vocalized?.trim() || w.word_ar?.trim() || undefined
  const shown = w.word_display.trim() || w.word.trim()
  if (!arabic) return { display: shown }
  return arabicUi || !shown ? { arabic } : { arabic, display: shown }
}

export function gameCardInput(share: ColophonShare, words: NotebookGameWord[] | undefined, t: T, lang: string): GameCardInput {
  const arabicUi = lang.startsWith("ar")
  const all = (words ?? []).map((w) => cardWord(w, arabicUi))
  const overflow = all.length > MAX_CARD_WORDS
  return {
    kind: "game",
    dir: dirOf(lang),
    arabicName: t(`home.fihrist.${GAME_KEY[share.game]}.arabic`),
    latinName: arabicUi ? undefined : gameName(share.game, t),
    meta: gameMetaParts(share, t),
    footer: SHARE_URL,
    words: overflow ? all.slice(0, MAX_CARD_WORDS - 1) : all,
    more: overflow ? t("game.colophon.share.more", { count: all.length - (MAX_CARD_WORDS - 1) }) : undefined,
  }
}

/** The line copied where the image cannot be shared (and sent with it): "Majlisna · Undercover · … · majlisna.app". */
export function gameShareLine(share: ColophonShare, t: T): string {
  return t("game.colophon.share.line", { meta: gameMetaParts(share, t).join(" · "), url: SHARE_URL })
}

/** The PNG's name, plain ASCII: "majlisna-undercover.png". */
export function gameCardFileName(share: ColophonShare): string {
  return `majlisna-${share.game}.png`
}
