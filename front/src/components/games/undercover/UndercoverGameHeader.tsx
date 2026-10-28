import { Eye } from "lucide-react"
import { memo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Chip } from "@/components/ui/chip"

interface UndercoverGameHeaderProps {
  round: number
  /** The phase on screen, for the line under the name ("Round 2 · the vote"). */
  phase: string
  isSpectator: boolean
  /** The thread clock, when the phase has a timer. */
  clock?: ReactNode
  /** The prayer pause control (<PauseControl />): renders nothing for whoever cannot use it. */
  pauseControl?: ReactNode
}

const PHASE_LINE: Record<string, string> = {
  role_reveal: "game.undercover.phaseLine.firstReading",
  describing: "game.undercover.phaseLine.describing",
  playing: "game.undercover.phaseLine.voting",
  round_over: "game.undercover.phaseLine.voting",
  mr_white_guessing: "game.undercover.phaseLine.guessing",
}

/**
 * The game's header (sketch D phones): the name (the page's h1: the E2E helpers wait for
 * `h1:has-text('Undercover')`), the round and what it is for, and the thread clock at the
 * inline end, after the host's prayer-pause control. Spectators see that they are watching.
 */
export const UndercoverGameHeader = memo(function UndercoverGameHeader({ round, phase, isSpectator, clock, pauseControl }: UndercoverGameHeaderProps) {
  const { t } = useTranslation()
  const line = phase === "game_over" ? t("game.undercover.phaseLine.end") : PHASE_LINE[phase] ? t(PHASE_LINE[phase], { round }) : null
  return (
    <header className="uc-head">
      <div className="min-w-0">
        <h1 className="type-panel text-[19px] sm:text-[21px]">{t("games.undercover.name")}</h1>
        {line ? <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{line}</p> : null}
      </div>
      <div className="ms-auto flex items-center gap-3">
        {isSpectator ? (
          <Chip tone="outline" mark={<Eye className="size-4" aria-hidden="true" />}>
            {t("game.spectating")}
          </Chip>
        ) : null}
        {pauseControl}
        {clock ? <div className="uc-clock">{clock}</div> : null}
      </div>
    </header>
  )
})
