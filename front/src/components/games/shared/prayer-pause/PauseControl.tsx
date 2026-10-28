import { Pause } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface PauseControlProps {
  /** The server's `can_pause` for this caller (the host, while the game runs). */
  canPause: boolean
  /** The server's `can_resume` for this caller. */
  canResume: boolean
  /** Whether the game is paused right now. */
  paused: boolean
  onPause: () => void
  onResume: () => void
  pending?: boolean
  className?: string
}

/**
 * The header's control for the prayer pause: "Pause" for the host while the game runs,
 * nothing otherwise. While the game is paused the veil carries the one Resume: the
 * header's own used to stay visible at about 10 % through the veil, a ghost of the real
 * button that could not be pressed (the game under the veil is inert). A quiet brass
 * hairline (secondary), never the screen's primary action. On phones only the icon
 * shows; the full name ("Pause the game for ṣalāh") is always its accessible name.
 *
 * `canResume` / `onResume` stay in the props so every game header passes the same set;
 * the veil (PauseLayer) is what offers them.
 */
export function PauseControl({ canPause, paused, onPause, pending = false, className }: PauseControlProps) {
  const { t } = useTranslation()
  if (paused || !canPause) return null
  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={onPause}
      loading={pending}
      aria-label={t("pause.pauseLabel")}
      iconStart={<Pause aria-hidden="true" />}
      className={cn("shrink-0 max-sm:px-3", className)}
      data-testid="pause-game"
    >
      <span className="max-sm:sr-only">{t("pause.pause")}</span>
    </Button>
  )
}
