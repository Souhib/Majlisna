import { UserMinus } from "lucide-react"
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

/**
 * Removing a friend asks first: on a phone the button sits under the thumb, and the
 * friendship cannot be restored without a new request and its acceptance.
 *
 * `compact` is the icon button of a list row; otherwise a labelled danger button (a
 * player's page).
 */
export function RemoveFriendButton({
  name,
  onConfirm,
  busy = false,
  compact = false,
}: {
  name: string
  onConfirm: () => void
  busy?: boolean
  compact?: boolean
}) {
  const { t } = useTranslation()
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        {compact ? (
          <Button
            variant="ghost"
            size="icon-sm"
            loading={busy}
            aria-label={t("friends.removeNamed", { name })}
            className="text-muted-foreground hover:text-ember"
          >
            {busy ? null : <UserMinus aria-hidden="true" />}
          </Button>
        ) : (
          <Button variant="danger" size="sm" loading={busy} iconStart={<UserMinus aria-hidden="true" />}>
            {t("friends.removeFriend")}
          </Button>
        )}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("friends.removeTitle", { name })}</AlertDialogTitle>
          <AlertDialogDescription>{t("friends.removeBody")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction variant="danger" onClick={onConfirm}>
            {t("friends.removeFriend")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
