import { Ban, UserMinus } from "lucide-react"
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

/** The host's two removals: Remove (a kick) and Ban. */
export type Removal = "kick" | "ban"

/** Each removal's words (`room.lobbyPage.*`) and icon. */
const REMOVAL_COPY = {
  kick: { label: "kick", title: "kickConfirmTitle", body: "kickConfirmBody", action: "kickConfirmAction", Icon: UserMinus },
  ban: { label: "ban", title: "banConfirmTitle", body: "banConfirmBody", action: "banConfirmAction", Icon: Ban },
} as const

interface RemovalConfirmButtonProps {
  how: Removal
  /** The player's username, in the button's name and the dialog. */
  name: string
  busy: boolean
  disabled: boolean
  /**
   * The dialog's text when it is not the roster's: a removed player (RoomBans, "Removed")
   * already left, so their Ban does not say they leave the room (`banRemovedConfirmBody`).
   */
  bodyKey?: "banRemovedConfirmBody"
  onConfirm: () => void
}

/**
 * One of the host's removal buttons: an icon button that opens its own confirmation,
 * portalled out of the row; nothing is sent before the dialog's action. The roster's Remove
 * and Ban (PlayerRoster) and the Ban of a removed player (RoomBans) are this one button, so
 * E2E clicks either by its name ("Ban {{name}} from the room"), then the dialog's "Ban". On
 * close Radix gives focus back to it; when its row goes, the list moves focus on by the
 * button's data attribute (`data-remove` / `data-ban`).
 */
export function RemovalConfirmButton({ how, name, busy, disabled, bodyKey, onConfirm }: RemovalConfirmButtonProps) {
  const { t } = useTranslation()
  const copy = REMOVAL_COPY[how]
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          loading={busy}
          disabled={disabled}
          data-remove={how === "kick" ? "" : undefined}
          data-ban={how === "ban" ? "" : undefined}
          aria-label={t(`room.lobbyPage.${copy.label}`, { name })}
          className="shrink-0 text-muted-foreground hover:bg-[color-mix(in_oklch,var(--ember)_10%,transparent)] hover:text-ember aria-busy:[&>svg]:hidden"
        >
          <copy.Icon aria-hidden="true" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t(`room.lobbyPage.${copy.title}`, { name })}</AlertDialogTitle>
          <AlertDialogDescription>{t(`room.lobbyPage.${bodyKey ?? copy.body}`, { name })}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction variant="danger" onClick={onConfirm}>
            {t(`room.lobbyPage.${copy.action}`)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
