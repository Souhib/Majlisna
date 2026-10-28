import { memo, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { type CardVoter, CardCell } from "./CardCell"
import { type CodenamesCard, type CodenamesPlayer, votersByCard } from "./model"

interface GameBoardProps {
  board: CodenamesCard[]
  isSpymaster: boolean
  canGuess: boolean
  isFinished: boolean
  onGuessCard: (index: number) => void
  /** user id → card index: who on the current team points at which card. */
  cardVotes?: Record<string, number>
  currentUserId?: string
  onHintViewed?: (word: string) => void
  /** The players, to name (and draw the initials of) whoever is pointing. */
  players?: CodenamesPlayer[]
  /** End of game: the words turned during play (the rest read as the key). */
  playedWords?: string[]
}

/**
 * The 5 × 5 board. Its order is the same in every language (left to right), so a
 * mixed table can say "the top-left card" and mean one card; each card's own text
 * follows the interface. Fits 390 px phones (five columns, the words scale to their
 * card) and opens up on wide screens (the cards keep a 3:2 cloth).
 */
export const GameBoard = memo(function GameBoard({
  board,
  isSpymaster,
  canGuess,
  isFinished,
  onGuessCard,
  cardVotes,
  currentUserId,
  onHintViewed,
  players,
  playedWords,
}: GameBoardProps) {
  const { t, i18n } = useTranslation()
  const arabicLeads = (i18n.language ?? "").startsWith("ar")

  const { voters, myVote } = useMemo(() => {
    const byCard = votersByCard(cardVotes)
    const names = new Map((players ?? []).map((p) => [p.user_id, p.username]))
    const out = new Map<number, CardVoter[]>()
    for (const [index, ids] of byCard) {
      out.set(
        index,
        ids.map((id) => ({ id, name: names.get(id) ?? "?" })),
      )
    }
    let mine: number | undefined
    if (cardVotes && currentUserId && typeof cardVotes[currentUserId] === "number") mine = cardVotes[currentUserId]
    return { voters: out, myVote: mine }
  }, [cardVotes, currentUserId, players])

  const played = useMemo(() => (isFinished && playedWords ? new Set(playedWords) : null), [isFinished, playedWords])

  return (
    <div className="cn-board-wrap">
      <div data-testid="codenames-board" role="group" aria-label={t("game.codenames.board")} className="cn-board" dir="ltr">
        {board.map((card, index) => (
          <CardCell
            key={index}
            card={card}
            index={index}
            isSpymaster={isSpymaster}
            canGuess={canGuess}
            isFinished={isFinished}
            onGuess={onGuessCard}
            voters={voters.get(index)}
            isMyVote={myVote === index}
            onHintViewed={onHintViewed}
            played={played ? played.has(card.word) : undefined}
            arabicLeads={arabicLeads}
          />
        ))}
      </div>
    </div>
  )
})
