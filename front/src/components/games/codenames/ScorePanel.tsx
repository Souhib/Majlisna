import { memo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { TeamGlyph } from "@/components/brand"
import { Chip } from "@/components/ui/chip"
import { cn } from "@/lib/utils"
import { type CodenamesTurn, type TeamId, teamWool } from "./model"

interface ScorePanelProps {
  redRemaining: number
  blueRemaining: number
  currentTeam: TeamId
  currentTurn: Pick<CodenamesTurn, "clue_word"> | null
  isMyTurn: boolean
  isFinished: boolean
  isSpymaster?: boolean
  winner?: TeamId | null
  /** Who you are at this table ("You are the Red spymaster"): <CodenamesMyInfo />. */
  myInfo?: ReactNode
  /** The thread clock, when the turn has one. */
  clock?: ReactNode
  /** The prayer pause control (<PauseControl />): renders nothing for whoever cannot use it. */
  pause?: ReactNode
}

/**
 * The board's header (sketch C panel head + sketch D phone top): the game's name and
 * who you are, the clock (and the host's prayer-pause control); the two teams as woven chips (swatch + glyph + words left)
 * and whose turn it is. On phones the clock sits beside the name and the turn beside
 * the chips; from 640 px the chips move up and the clock runs under them.
 */
export const ScorePanel = memo(function ScorePanel({
  redRemaining,
  blueRemaining,
  currentTeam,
  currentTurn,
  isMyTurn,
  isFinished,
  isSpymaster = false,
  winner = null,
  myInfo,
  clock,
  pause,
}: ScorePanelProps) {
  const { t } = useTranslation()
  const teamName = (team: TeamId) => t(`game.codenames.teams.${team}`)
  const clueGiven = !!currentTurn?.clue_word

  let status: string
  let statusTeam: TeamId = currentTeam
  let yours = false
  if (isFinished && winner) {
    status = t("game.codenames.status.won", { team: teamName(winner) })
    statusTeam = winner
  } else if (!clueGiven) {
    yours = isMyTurn && isSpymaster
    status = yours ? t("game.codenames.status.yourClue") : t("game.codenames.status.theirClue", { team: teamName(currentTeam) })
  } else {
    yours = isMyTurn && !isSpymaster
    status = yours ? t("game.codenames.status.yourGuess") : t("game.codenames.status.guessing", { team: teamName(currentTeam) })
  }

  return (
    <header className="cn-head">
      <div className="cn-head-title flex flex-col gap-x-3.5 gap-y-1 sm:flex-row sm:flex-wrap sm:items-baseline">
        <h1 className="type-panel sm:text-[19px]">{t("games.codenames.name")}</h1>
        {myInfo}
      </div>
      {/* the host's pause: beside the clock on phones, at the end of the first row from 640 px */}
      <div className="order-2 flex flex-none empty:hidden sm:order-3">{pause}</div>
      <div className="cn-head-clock">{clock}</div>
      <span className="cn-head-break" aria-hidden="true" />
      <div className="cn-head-teams" role="group" aria-label={t("game.codenames.wordsLeft")}>
        <TeamChip team="red" name={teamName("red")} count={redRemaining} />
        <TeamChip team="blue" name={teamName("blue")} count={blueRemaining} />
      </div>
      {/* At the end the colophon's title says who won ("The Blue team wins."): the line
          here would print it a second time beside it, so it is only spoken (still the
          live line that announces the end), not shown. */}
      <p
        className={cn(
          "cn-head-status flex items-center gap-2 text-[13.5px] leading-snug sm:text-[14.5px]",
          yours ? "font-medium text-brass" : "text-muted-foreground",
          isFinished && "sr-only",
        )}
        aria-live="polite"
      >
        <TeamGlyph team={teamWool(statusTeam)} className="hidden sm:block" />
        <span>{status}</span>
      </p>
    </header>
  )
})

function TeamChip({ team, name, count }: { team: TeamId; name: string; count: number }) {
  const { t } = useTranslation()
  const wool = teamWool(team)
  return (
    <Chip swatch={wool === "madder" ? "teeth" : "ayn"} mark={<TeamGlyph team={wool} className="text-muted-foreground" />}>
      <span className="max-sm:sr-only">{name}</span>
      <b className="num font-medium" aria-hidden="true">
        {count}
      </b>
      <span className="sr-only">{t("game.codenames.left", { count })}</span>
    </Chip>
  )
}
