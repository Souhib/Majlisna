import { LogOut } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"

interface UndercoverLeaveButtonProps {
  onLeave: () => void
  /** A spectator only stops watching: no seat empties. */
  isSpectator?: boolean
  /** The player's seat already emptied (voted out): leaving takes nothing from the table. */
  isEliminated?: boolean
}

/**
 * "Leave the room" (the one label of every leave). Leaving mid-game empties a seat for
 * everyone, so it asks first (an AlertDialog: it
 * cannot be dismissed by a stray tap outside).
 */
export const UndercoverLeaveButton = memo(function UndercoverLeaveButton({ onLeave, isSpectator = false, isEliminated = false }: UndercoverLeaveButtonProps) {
  const { t } = useTranslation()
  return (
    <div className="border-t border-line pt-4">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="ghost" size="sm" className="-ms-2 text-muted-foreground" iconStart={<LogOut className="rtl-flip" aria-hidden="true" />}>
            {t("room.lobbyPage.leave")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("game.undercover.leaveConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {isSpectator
                ? t("game.undercover.leaveConfirmBodySpectator")
                : isEliminated
                  ? t("game.undercover.leaveConfirmBodyOut")
                  : t("game.undercover.leaveConfirmBody")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("game.undercover.stay")}</AlertDialogCancel>
            <AlertDialogAction variant="danger" onClick={onLeave}>
              {t("room.lobbyPage.leave")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
})
