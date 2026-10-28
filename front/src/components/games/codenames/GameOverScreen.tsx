import { memo, useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Colophon, type ColophonWord, TeamGlyph } from "@/components/brand"
import { useAchievementSeals } from "@/components/games/shared/achievement-seals"
import { ColophonActions } from "@/components/games/shared/ColophonActions"
import { ColophonMeta, type GameColophon } from "@/components/games/shared/ColophonMeta"
import { KeepWordToggle } from "@/components/notebook/KeepWords"
import { useRouteNotebookGameId } from "@/components/notebook/route-game"
import { useColophonNotebook } from "@/components/notebook/use-colophon-notebook"
import { cn } from "@/lib/utils"
import { arabicForm, cardGlyph, type ClueHistoryEntry, type CodenamesCard, type CodenamesPlayer, endReason, otherTeam, playedWords, type TeamId } from "./model"

export interface UnlockedAchievements {
  user_id: string
  achievements: { code: string; name: string; icon?: string; tier: number }[]
}

interface GameOverScreenProps {
  winner: TeamId
  roomId: string | null
  board?: CodenamesCard[]
  onBackToRoom: () => void
  onLeaveRoom: () => void
  history?: ClueHistoryEntry[]
  players?: CodenamesPlayer[]
  remaining?: { red: number; blue: number }
  /** Everyone's achievements from this game: pressed as seals, never toasted. */
  achievements?: UnlockedAchievements[] | null
  currentUserId?: string
  /** The viewer hosts the room: only they get "Play again" (the server refuses anyone else). */
  isHost?: boolean
  /** The game, for the notebook. Defaults to the id in the page's URL (`/game/codenames/<id>`). */
  gameId?: string
  /** Who hosted it and when it ran (the state's `host_username`, `started_at`, `ended_at`). */
  colophon?: GameColophon
}

/**
 * The colophon (sketch H): who won and how, the words the table turned with their
 * meaning (the rest of the board one tap away), a brass seal for every achievement
 * earned at this table, and the way on. A visually hidden <h2>Game Over</h2> keeps
 * the heading the E2E suite waits for; the visible title is the sentence.
 *
 * The Kunnash: a player of the game (not a spectator, who is not in `players`) keeps
 * the 25 words with "Keep the words" (the brass action until they are all kept) or one
 * by one with the toggle at the end of each row, the turned words and the rest of the
 * board alike. The actions are the four games' `ColophonActions`: everyone gets "Back to
 * the room", only the host "Play again".
 */
export const GameOverScreen = memo(function GameOverScreen({
  winner,
  roomId,
  board,
  onBackToRoom,
  onLeaveRoom,
  history,
  players,
  remaining,
  achievements,
  currentUserId,
  isHost = false,
  gameId,
  colophon,
}: GameOverScreenProps) {
  const { t, i18n } = useTranslation()
  const arabicUi = (i18n.language ?? "").startsWith("ar")

  // a spectator is not among the players (the server would answer 403 anyway)
  const isPlayer = !players || !currentUserId || players.some((p) => p.user_id === currentUserId)
  const routeGameId = useRouteNotebookGameId("codenames")
  const notebook = useColophonNotebook(gameId ?? routeGameId, { enabled: isPlayer })

  const teamName = useCallback((team: TeamId) => t(`game.codenames.teams.${team}`), [t])
  const loser = otherTeam(winner)

  const summary = useMemo(() => {
    if (!remaining) return null
    switch (endReason(winner, remaining, history)) {
      case "all-found":
        return t("game.codenames.over.allFound", { team: teamName(winner), other: teamName(loser), count: remaining[loser] })
      case "assassin":
        return t("game.codenames.over.assassin", { other: teamName(loser) })
      default:
        return t("game.codenames.over.forfeit", { other: teamName(loser) })
    }
  }, [remaining, winner, loser, history, t, teamName])

  const { played, rest } = useMemo(() => {
    const cards = board ?? []
    const byWord = new Map(cards.map((c) => [c.word, c]))
    const order = playedWords(history)
    const turned = order.map((w) => byWord.get(w)).filter((c): c is CodenamesCard => !!c)
    const turnedSet = new Set(order)
    return { played: turned, rest: cards.filter((c) => !turnedSet.has(c.word)) }
  }, [board, history])

  const clueOf = useMemo(() => {
    const map = new Map<string, string>()
    for (const entry of history ?? []) for (const g of entry.guesses) if (!map.has(g.word)) map.set(g.word, entry.clue_word)
    return map
  }, [history])

  const toWord = useCallback(
    (card: CodenamesCard): ColophonWord => {
      const ar = arabicForm(card)
      const glyph = cardGlyph(card.card_type)
      const clue = clueOf.get(card.word)
      return {
        word: ar ?? undefined,
        // no transliteration in the Arabic interface, unless the word has no Arabic form
        translit: arabicUi && ar ? undefined : card.word,
        note: (
          <span className="inline-flex items-center gap-1.5">
            {glyph ? <TeamGlyph team={glyph} size={10} /> : null}
            <span>{t(`game.codenames.card.${glyph ?? "bystander"}`)}</span>
            {clue ? (
              <span className="max-sm:hidden">
                {" · "}
                {t("game.codenames.over.onClue", { clue })}
              </span>
            ) : null}
          </span>
        ),
        meaning: card.hint ?? undefined,
        action: notebook.find(card.word) ? <KeepWordToggle notebook={notebook} word={card.word} label={arabicUi && ar ? ar : card.word} /> : undefined,
      }
    },
    [arabicUi, clueOf, notebook, t],
  )

  // One seal per achievement, captioned with everyone who earned it at this table (you first).
  const seals = useAchievementSeals(achievements, players, currentUserId)

  // "Codenames · Yusuf’s majlis · 9 clues · 14:05" (sketch H): the turned words are listed below
  const clues = history?.length ?? 0
  const meta = (
    <ColophonMeta
      game={t("games.codenames.name")}
      host={colophon?.hostUsername}
      count={clues > 0 ? t("game.codenames.over.clues", { count: clues }) : null}
      startedAt={colophon?.startedAt}
      endedAt={colophon?.endedAt}
    />
  )

  return (
    <div>
      <h2 className="sr-only">{t("game.gameOver")}</h2>
      <Colophon
        title={t("game.codenames.over.title", { team: teamName(winner) })}
        titleAs="h3"
        summary={summary}
        meta={meta}
        words={played.map(toWord)}
        seals={seals}
        actions={<ColophonActions notebook={notebook} roomId={roomId} isHost={isHost} onBackToRoom={onBackToRoom} onLeaveRoom={onLeaveRoom} />}
      >
        {rest.length > 0 ? (
          <details className="cn-more">
            <summary>{t(played.length > 0 ? "game.codenames.over.otherWords" : "game.codenames.over.allWords", { count: rest.length })}</summary>
            <ul className="mt-1 border-t border-line">
              {rest.map((card) => {
                const ar = arabicForm(card)
                const glyph = cardGlyph(card.card_type)
                const keep = notebook.find(card.word) ? <KeepWordToggle notebook={notebook} word={card.word} label={arabicUi && ar ? ar : card.word} /> : null
                return (
                  <li
                    key={card.word}
                    className={cn(
                      "grid items-baseline gap-x-3 border-b border-line py-2",
                      keep ? "grid-cols-[auto_minmax(0,1fr)_auto]" : "grid-cols-[auto_1fr]",
                    )}
                  >
                    <span className="flex items-center gap-1.5 self-center">
                      {glyph ? (
                        <TeamGlyph
                          team={glyph}
                          size={10}
                          className={glyph === "assassin" ? undefined : "text-muted-foreground"}
                          label={t(`game.codenames.card.${glyph}`)}
                        />
                      ) : null}
                    </span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-baseline gap-x-2">
                        {ar ? (
                          <span lang="ar" dir="rtl" className="font-nass text-[20px] font-bold leading-[1.5]">
                            {ar}
                          </span>
                        ) : null}
                        {!(arabicUi && ar) ? <span className="text-[14px] font-medium">{card.word}</span> : null}
                      </span>
                      {card.hint ? <span className="block text-[13px] leading-[1.4] text-muted-foreground">{card.hint}</span> : null}
                    </span>
                    {keep ? <span className="self-center">{keep}</span> : null}
                  </li>
                )
              })}
            </ul>
          </details>
        ) : null}
      </Colophon>
    </div>
  )
})
