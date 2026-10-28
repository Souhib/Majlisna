import { Link } from "@tanstack/react-router"
import { Check } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useGetFriendsApiV1FriendsGet, useInviteFriendToRoomApiV1RoomsRoomIdInvitePost } from "@/api/generated"
import { Avatar } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState } from "@/components/ui/empty-state"
import { Skeleton } from "@/components/ui/skeleton"
import { roomErrorMessage } from "./errors"

interface InviteFriendModalProps {
  roomId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Invite a friend into the room (Dialog: protected focus, Escape and the corner button
 * close it, focus returns to "Invite a friend"). Each friend gets one Invite button,
 * which turns into a quiet "Invited" once the notice has gone out.
 */
export function InviteFriendModal({ roomId, open, onOpenChange }: InviteFriendModalProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("room.lobbyPage.invite")}</DialogTitle>
          <DialogDescription>{t("room.invite.description")}</DialogDescription>
        </DialogHeader>
        {open ? <FriendList roomId={roomId} /> : null}
      </DialogContent>
    </Dialog>
  )
}

function FriendList({ roomId }: { roomId: string }) {
  const { t } = useTranslation()
  const [invitedIds, setInvitedIds] = useState<Set<string>>(new Set())
  const [invitingId, setInvitingId] = useState<string | null>(null)
  const { data: friends = [], isLoading } = useGetFriendsApiV1FriendsGet()
  const inviteMutation = useInviteFriendToRoomApiV1RoomsRoomIdInvitePost()

  const handleInvite = async (friendUserId: string) => {
    setInvitingId(friendUserId)
    try {
      await inviteMutation.mutateAsync({ room_id: roomId, data: { friend_user_id: friendUserId } })
      setInvitedIds((prev) => new Set(prev).add(friendUserId))
      toast.success(t("room.inviteSent"))
    } catch (err) {
      toast.error(roomErrorMessage(err, t("room.invite.failed")))
    } finally {
      setInvitingId(null)
    }
  }

  if (isLoading) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <span className="sr-only">{t("common.loading")}</span>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (friends.length === 0) {
    return (
      <EmptyState
        className="py-6"
        titleAs="p"
        title={t("room.invite.emptyTitle")}
        description={t("room.invite.emptyBody")}
        action={
          <Button asChild variant="secondary" size="sm">
            <Link to="/friends">{t("nav.friends")}</Link>
          </Button>
        }
      />
    )
  }

  return (
    <ul className="-mx-1 grid max-h-[50dvh] overflow-y-auto border-t border-line px-1">
      {friends.map((friend) => {
        const isInvited = invitedIds.has(friend.user_id)
        const isInviting = invitingId === friend.user_id
        return (
          <li key={friend.friendship_id} className="flex items-center gap-3 border-b border-line py-2.5">
            <Avatar name={friend.username} size={36} />
            <span className="min-w-0 flex-1 truncate text-[15px] font-medium">
              <bdi>{friend.username}</bdi>
            </span>
            {isInvited ? (
              <span className="inline-flex h-10 items-center gap-1.5 px-2 text-[14px] text-muted-foreground" role="status">
                <Check className="size-4 text-brass" aria-hidden="true" />
                {t("room.invite.sent")}
              </span>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                loading={isInviting}
                disabled={invitingId !== null && !isInviting}
                onClick={() => handleInvite(friend.user_id)}
                aria-label={t("room.invite.actionLabel", { name: friend.username })}
              >
                {t("room.invite.action")}
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
