import { Trans, useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand/Lozenge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface RoomInvite {
  roomId: string
  publicId: string
  password: string
  invitedBy: string
}

interface RoomInviteStripProps {
  invite: RoomInvite
  onJoin: () => void
  onDismiss: () => void
  className?: string
}

/**
 * A friend's invitation to their room, as a quiet strip at the top of the page: "Yusuf
 * invites you to their majlis" [Join] [Not now]. Not a toast: the player did not cause
 * it (toasts are only for the result of their own action). It is announced politely,
 * takes no focus and stays until answered; the shell keeps only the latest one and
 * holds it back while a game is on screen.
 */
export function RoomInviteStrip({ invite, onJoin, onDismiss, className }: RoomInviteStripProps) {
  const { t } = useTranslation()
  return (
    <section
      aria-label={t("room.inviteLabel")}
      data-testid="room-invite"
      className={cn(
        "flex animate-fade-in flex-wrap items-center gap-x-4 gap-y-2.5 rounded-lg border border-line-brass bg-surface px-4 py-3",
        className,
      )}
    >
      <p role="status" className="flex min-w-0 flex-[1_1_16rem] items-baseline gap-2.5 text-[15px] leading-snug">
        <Lozenge state="brass" size={7} className="relative -top-px" />
        <span className="min-w-0 break-words [&_b]:font-medium">
          <Trans i18nKey="room.inviteReceived" values={{ username: invite.invitedBy }} components={{ b: <b dir="auto" /> }} />
        </span>
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={onJoin}>
          {t("room.joinInvite")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          {t("room.inviteLater")}
        </Button>
      </div>
    </section>
  )
}
