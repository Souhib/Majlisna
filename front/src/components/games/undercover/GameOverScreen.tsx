import { memo, type ReactNode, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Colophon, type ColophonSeal, type ColophonWord } from "@/components/brand"
import { ColophonActions } from "@/components/games/shared/ColophonActions"
import { ColophonMeta, type GameColophon } from "@/components/games/shared/ColophonMeta"
import { KeepWordToggle } from "@/components/notebook/KeepWords"
import { useRouteNotebookGameId } from "@/components/notebook/route-game"
import { useColophonNotebook } from "@/components/notebook/use-colophon-notebook"
import { formatNames, type VerdictRound } from "./Verdict"

interface WordExplanations {
  civilian_word: string
  civilian_word_ar?: string | null
  civilian_word_ar_vocalized?: string | null
  civilian_word_hint: string | null
  undercover_word: string
  undercover_word_ar?: string | null
  undercover_word_ar_vocalized?: string | null
  undercover_word_hint: string | null
}

interface UnlockedAchievement {
  code: string
  name: string
  icon?: string
  tier?: number
}

export interface PlayerAchievements {
  user_id: string
  achievements: UnlockedAchievement[]
}

interface GameOverScreenProps {
  winner?: string
  roomId: string | null
  isHost?: boolean
  /** Your role ("spectator" for a spectator): at the end, your own side is told. */
  myRole?: string
  players?: { id: string; username: string }[]
  voteHistory?: VerdictRound[]
  rounds?: number
  wordExplanations?: WordExplanations | null
  achievements?: PlayerAchievements[] | null
  onBackToRoom: () => void
  onLeaveRoom: () => void
  /** Slot at the head of the actions row. */
  extraActions?: ReactNode
  /** The game, for the notebook. Defaults to the id in the page's URL (`/game/undercover/<id>`). */
  gameId?: string
  /** Who hosted it and when it ran (the state's `host_username`, `started_at`, `ended_at`). */
  colophon?: GameColophon
}

/**
 * Game over: the colophon in the arch (DESIGN.md §6, sketch H). "The table found Bilal.",
 * who won and what you held, the two words with their meaning, the achievements earned
 * this game as brass seals (never mid-game toasts), then the way back.
 *
 * The Kunnash: a player (never a spectator) can keep the two words, both at once with
 * "Keep the words" (the brass action while some word is not kept) or one by one with the
 * toggle at the end of each word row. The actions are the four games' `ColophonActions`.
 *
 * The title is an h2 that starts with a visually hidden "Game Over" (E2E waits for
 * `h2:has-text("Game Over")`; screen readers hear it first).
 */
export const GameOverScreen = memo(function GameOverScreen({
  winner,
  roomId,
  isHost = false,
  myRole,
  players = [],
  voteHistory = [],
  rounds,
  wordExplanations,
  achievements,
  onBackToRoom,
  onLeaveRoom,
  extraActions,
  gameId,
  colophon,
}: GameOverScreenProps) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language ?? "en"
  const arabicUi = lang.startsWith("ar")

  const routeGameId = useRouteNotebookGameId("undercover")
  const notebook = useColophonNotebook(gameId ?? routeGameId, { enabled: myRole !== "spectator" })

  // Who was found: every impostor the table voted out, in the order it happened.
  const found = useMemo(
    () =>
      voteHistory
        .map((r) => r.eliminated)
        .filter((e): e is NonNullable<typeof e> => !!e && e.role !== "civilian")
        .map((e) => e.username),
    [voteHistory],
  )

  const sentence =
    winner === "civilians"
      ? found.length > 0
        ? t("game.undercover.colophon.found", { names: formatNames(found, lang) })
        : t("game.undercover.colophon.tableHeld")
      : winner === "undercovers"
        ? t("game.undercover.colophon.otherWordHeld")
        : null

  const title = sentence ? (
    <>
      <span className="sr-only">{t("game.gameOver")}. </span>
      {sentence}
    </>
  ) : (
    t("game.gameOver")
  )

  const youHeld =
    myRole === "civilian"
      ? t("game.undercover.colophon.youCivilian")
      : myRole === "undercover"
        ? t("game.undercover.colophon.youUndercover")
        : myRole === "mr_white"
          ? t("game.undercover.colophon.youMrWhite")
          : null
  const result =
    winner === "civilians" ? t("game.undercover.colophon.civiliansWin") : winner === "undercovers" ? t("game.undercover.colophon.impostorsWin") : null
  const summary = [result, youHeld].filter(Boolean).join(" ") || undefined

  // "Undercover · Yusuf’s majlis · 3 rounds · 21:40" (sketch H)
  const meta = (
    <ColophonMeta
      game={t("games.undercover.name")}
      host={colophon?.hostUsername}
      count={rounds ? t("game.undercover.colophon.rounds", { count: rounds }) : null}
      startedAt={colophon?.startedAt}
      endedAt={colophon?.endedAt}
    />
  )

  const words: ColophonWord[] = []
  if (wordExplanations) {
    const pair = [
      {
        latin: wordExplanations.civilian_word,
        arabic: wordExplanations.civilian_word_ar_vocalized || wordExplanations.civilian_word_ar,
        hint: wordExplanations.civilian_word_hint,
        note: t("game.undercover.colophon.tableWord"),
      },
      {
        latin: wordExplanations.undercover_word,
        arabic: wordExplanations.undercover_word_ar_vocalized || wordExplanations.undercover_word_ar,
        hint: wordExplanations.undercover_word_hint,
        note: t("game.undercover.colophon.otherWord"),
      },
    ]
    for (const w of pair) {
      const keep = notebook.find(w.latin) ? <KeepWordToggle notebook={notebook} word={w.latin} label={arabicUi && w.arabic ? w.arabic : w.latin} /> : undefined
      words.push({
        word: w.arabic || undefined,
        // no transliteration in the Arabic interface, unless there is nothing else to show
        translit: arabicUi && w.arabic ? undefined : w.latin,
        note: w.note,
        // the server can fall back to another language for a meaning: let it keep its own direction
        meaning: w.hint ? <span dir="auto">{w.hint}</span> : undefined,
        action: keep,
      })
    }
  }

  // One seal per achievement, captioned with whoever earned it this game.
  const seals: ColophonSeal[] = useMemo(() => {
    if (!achievements?.length) return []
    const names = new Map(players.map((p) => [p.id, p.username]))
    const byCode = new Map<string, { name: string; holders: string[] }>()
    for (const entry of achievements) {
      const holder = names.get(entry.user_id)
      for (const a of entry.achievements) {
        const seal = byCode.get(a.code) ?? { name: a.name, holders: [] }
        if (holder && !seal.holders.includes(holder)) seal.holders.push(holder)
        byCode.set(a.code, seal)
      }
    }
    return [...byCode.entries()].map(([code, s]) => ({
      title: t(`achievements.items.${code}.name`, { defaultValue: s.name }),
      caption:
        players.length > 1 && s.holders.length === players.length
          ? t("game.undercover.colophon.wholeTable")
          : s.holders.length > 0
            ? formatNames(s.holders, lang)
            : undefined,
    }))
  }, [achievements, players, t, lang])

  const actions = (
    <>
      {extraActions}
      <ColophonActions notebook={notebook} roomId={roomId} isHost={isHost} onBackToRoom={onBackToRoom} onLeaveRoom={onLeaveRoom} />
    </>
  )

  return <Colophon title={title} summary={summary} meta={meta} words={words} seals={seals} actions={actions} />
})
