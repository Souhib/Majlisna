import { ArrowRight } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import type { RoomInviteView } from "@/api/generated"
import { Lozenge } from "@/components/brand/Lozenge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { isFinalInviteRefusal } from "./errors"
import { useAcceptInvite } from "./use-join-room"

interface RoomInviteStripProps {
  invite: RoomInviteView
  /** Seated: the shell opens the room's lobby. */
  onJoined: (roomId: string) => void
  onDismiss: () => void
  className?: string
}

/**
 * A friend's invitation to their room, as a quiet strip at the top of the page: "Yusuf
 * invites you to their majlis" [Join] [Not now]. Not a toast: the player did not cause
 * it (toasts are only for the result of their own action). It is announced politely,
 * takes no focus and stays until answered; the shell keeps only the latest one and
 * holds it back while a game is on screen.
 *
 * Join accepts the invite itself (`POST /rooms/invites/{id}/accept`): it is stored on the
 * server and carries no PIN, so a ban that rotated the PIN after it was sent does not
 * stop it. A refusal that holds (a ban, an expired invite, one no longer valid — deleted
 * by a ban of its sender, say — a closed room) is said on the strip in the server's words, and then
 * only Close is offered; a seat in another room is offered "Leave {{room}} and join"
 * (`useAcceptInvite`). Any other failure (a 429, a 5xx, no answer at all) is said too but
 * keeps Join, to try again: the invite still stands.
 */
export function RoomInviteStrip({ invite, onJoined, onDismiss, className }: RoomInviteStripProps) {
  const { t } = useTranslation()
  const flow = useAcceptInvite(onJoined)
  const { error, errorKey, seatElsewhere } = flow
  // the server's final word: asking again changes nothing
  const refused = isFinalInviteRefusal(errorKey)
  return (
    <section
      aria-label={t("room.inviteLabel")}
      data-testid="room-invite"
      className={cn("flex animate-fade-in flex-wrap items-center gap-x-4 gap-y-2.5 rounded-lg border border-line-brass bg-surface px-4 py-3", className)}
    >
      <p role="status" className="flex min-w-0 flex-[1_1_16rem] items-baseline gap-2.5 text-[15px] leading-snug">
        <Lozenge state="brass" size={7} className="relative -top-px" />
        <span className="min-w-0 break-words [&_b]:font-medium">
          <Trans i18nKey="room.inviteReceived" values={{ username: invite.invited_by }} components={{ b: <b dir="auto" /> }} />
        </span>
      </p>
      {error ? (
        <p role="alert" data-testid="room-invite-error" className="basis-full text-[15px] leading-normal text-ember">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {seatElsewhere ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void flow.leaveAndAccept()}
            loading={flow.busy || !seatElsewhere.code}
            iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
          >
            {t("room.joinPage.leaveAndJoin", { room: seatElsewhere.code ?? "…" })}
          </Button>
        ) : refused ? null : (
          <Button size="sm" variant="secondary" onClick={() => void flow.accept(invite.id)} loading={flow.busy}>
            {t("room.joinInvite")}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          {refused ? t("common.close") : t("room.inviteLater")}
        </Button>
      </div>
    </section>
  )
}
