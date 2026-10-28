import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

const ANNOUNCEMENT: Record<string, string> = {
  describing: "game.undercover.announce.describing",
  playing: "game.undercover.announce.voting",
  round_over: "game.undercover.announce.roundOver",
  mr_white_guessing: "game.undercover.announce.guessing",
  game_over: "game.undercover.announce.gameOver",
}

/**
 * Phase changes, spoken. The screens swap through a view transition (a 180 ms crossfade,
 * see lib/view-transition.ts), which replaces the old full-screen "All hints are in!" and
 * "Game Over" interstitials; this polite live region tells screen-reader users what the
 * crossfade shows. Silent on the first render, so a reload announces nothing.
 */
export function PhaseAnnouncer({ phase }: { phase: string }) {
  const { t } = useTranslation()
  const [message, setMessage] = useState("")
  const previous = useRef(phase)
  useEffect(() => {
    if (previous.current === phase) return
    previous.current = phase
    setMessage(ANNOUNCEMENT[phase] ? t(ANNOUNCEMENT[phase]) : "")
  }, [phase, t])
  return (
    <p className="sr-only" aria-live="polite">
      {message}
    </p>
  )
}
