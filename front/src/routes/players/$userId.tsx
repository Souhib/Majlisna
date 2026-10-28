import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Check, UserPlus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  useAcceptFriendRequestApiV1FriendsFriendshipIdAcceptPost,
  useGetFriendshipStatusApiV1FriendsStatusUserIdGet,
  useGetHeadToHeadApiV1StatsUsersUserIdVsOpponentIdGet,
  useGetPublicProfileApiV1ProfilesUsersUserIdGet,
  useGetUserByIdApiV1UsersUserIdGet,
  useRemoveFriendApiV1FriendsFriendshipIdDelete,
  useSendFriendRequestApiV1FriendsRequestPost,
} from "@/api/generated"
import type { HeadToHeadStats, PublicProfile } from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { Lozenge } from "@/components/brand"
import { RemoveFriendButton } from "@/components/friends/RemoveFriendButton"
import { currentLanguage } from "@/components/layout/language-switch"
import { countryName } from "@/components/profile/countries"
import { gameName } from "@/components/stats/format"
import { PlayLinks } from "@/components/stats/PlayLinks"
import { Figures } from "@/components/stats/PlayerSpace"
import { Avatar } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Chip } from "@/components/ui/chip"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocumentTitle } from "@/hooks/use-document-title"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/players/$userId")({
  component: PlayerProfilePage,
})

/**
 * A player's public page: who they are, what they play, and, for a signed-in visitor,
 * the record between the two of you and the friendship action.
 */
function PlayerProfilePage() {
  const { userId } = Route.useParams()
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const isOwnProfile = user?.id === userId
  const signedIn = Boolean(user?.id)

  const { data: profile, isLoading, error: queryError } = useGetPublicProfileApiV1ProfilesUsersUserIdGet({ user_id: userId }) as {
    data: PublicProfile | undefined
    isLoading: boolean
    error: Error | null
  }
  // country and photo live on the user record, which only a signed-in visitor may read
  const { data: details } = useGetUserByIdApiV1UsersUserIdGet({ user_id: userId }, { query: { enabled: signedIn } })
  const { data: friendshipStatus } = useGetFriendshipStatusApiV1FriendsStatusUserIdGet(
    { user_id: userId },
    { query: { enabled: signedIn && !isOwnProfile } },
  )
  const { data: h2h } = useGetHeadToHeadApiV1StatsUsersUserIdVsOpponentIdGet(
    { user_id: user?.id ?? "", opponent_id: userId },
    { query: { enabled: signedIn && !isOwnProfile } },
  ) as { data: HeadToHeadStats | undefined }
  // the tab names the player, as the page's heading does
  useDocumentTitle(profile?.username)

  const sendRequestMutation = useSendFriendRequestApiV1FriendsRequestPost()
  const acceptMutation = useAcceptFriendRequestApiV1FriendsFriendshipIdAcceptPost()
  const removeFriendMutation = useRemoveFriendApiV1FriendsFriendshipIdDelete()

  const refreshFriendship = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.friends.status(userId) })
    queryClient.invalidateQueries({ queryKey: queryKeys.friends.list() })
    queryClient.invalidateQueries({ queryKey: queryKeys.friends.pending() })
  }

  const handleAddFriend = async () => {
    if (sendRequestMutation.isPending) return
    try {
      await sendRequestMutation.mutateAsync({ data: { addressee_id: userId } })
      toast.success(t("friends.requestSent"))
      refreshFriendship()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    }
  }

  // They asked first: accept their request (it used to send one back, which the server
  // turned into an acceptance while the toast said "request sent").
  const handleAccept = async () => {
    if (acceptMutation.isPending || !friendshipStatus?.friendship_id) return
    try {
      await acceptMutation.mutateAsync({ friendship_id: friendshipStatus.friendship_id })
      toast.success(t("friends.requestAccepted"))
      refreshFriendship()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    }
  }

  const handleRemoveFriend = async () => {
    if (removeFriendMutation.isPending || !friendshipStatus?.friendship_id) return
    try {
      await removeFriendMutation.mutateAsync({ friendship_id: friendshipStatus.friendship_id })
      toast.success(t("friends.friendRemoved"))
      refreshFriendship()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    }
  }

  if (isLoading) {
    return (
      <div className="page-wrap py-[clamp(32px,5vw,72px)]" aria-busy="true">
        <div className="mx-auto grid max-w-[60rem] gap-6">
          <div className="flex items-center gap-5">
            <Skeleton className="size-[72px] rounded-full" />
            <Skeleton className="h-10 w-56" />
          </div>
          <Skeleton className="h-[106px] w-full" />
        </div>
      </div>
    )
  }

  if (queryError || !profile) {
    return (
      <div className="page-wrap py-[clamp(32px,5vw,72px)]">
        <Panel className="mx-auto max-w-[40rem]">
          <EmptyState
            titleAs="h1"
            title={t("profile.playerNotFound")}
            description={queryError ? getApiErrorMessage(queryError, t("common.error")) : undefined}
            action={
              <Button asChild variant="secondary">
                <Link to="/leaderboard">{t("leaderboard.title")}</Link>
              </Button>
            }
          />
        </Panel>
      </div>
    )
  }

  const status = friendshipStatus?.status
  const country = countryName(details?.country, i18n.language)
  const favourite = profile.favorite_game ? gameName(profile.favorite_game, t) : null
  // a name or bio keeps its own direction (dir="auto") but lines up with the page
  const pageAlign = currentLanguage(i18n.language) === "ar" ? "text-right" : "text-left"

  let action = null
  if (signedIn && !isOwnProfile) {
    if (status === "none") {
      action = (
        <Button size="sm" iconStart={<UserPlus aria-hidden="true" />} loading={sendRequestMutation.isPending} onClick={handleAddFriend}>
          {t("friends.addFriend")}
        </Button>
      )
    } else if (status === "pending_sent") {
      action = (
        <Chip tone="outline" mark={<Lozenge state="open" size={8} />}>
          {t("friends.requestPending")}
        </Chip>
      )
    } else if (status === "pending_received") {
      action = (
        <Button size="sm" iconStart={<Check aria-hidden="true" />} loading={acceptMutation.isPending} onClick={handleAccept}>
          {t("friends.acceptRequest")}
        </Button>
      )
    } else if (status === "accepted") {
      action = (
        <>
          <Chip tone="brass" mark={<Lozenge state="brass" size={8} />}>
            {t("stats.alreadyFriends")}
          </Chip>
          <RemoveFriendButton name={profile.username} busy={removeFriendMutation.isPending} onConfirm={handleRemoveFriend} />
        </>
      )
    }
  }

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <div className="mx-auto grid max-w-[60rem] gap-[clamp(20px,2.5vw,32px)]">
        <header className="flex flex-wrap items-center gap-x-5 gap-y-4">
          <Avatar name={profile.username} src={details?.profile_picture_url} size={72} decorative />
          <div className="grid min-w-0 flex-1 basis-56 gap-1.5">
            {/* the display role, like every page title: figures are Readex (Samar Figures), an Arabic name falls to Amiri */}
            <h1 dir="auto" className={cn(pageAlign, "type-title break-words text-[clamp(30px,2.8vw,42px)] leading-[1.15]")}>
              {profile.username}
            </h1>
            {country || favourite ? (
              <p className="flex flex-wrap gap-x-3 text-[14.5px] text-muted-foreground">
                {country ? <span>{country}</span> : null}
                {favourite ? <span>{t("profile.favouriteLine", { game: favourite })}</span> : null}
              </p>
            ) : null}
          </div>
          {action ? <div className="flex flex-wrap items-center gap-2.5">{action}</div> : null}
        </header>
        {profile.bio ? (
          <p dir="auto" className={cn(pageAlign, "-mt-2 max-w-[60ch] text-[16.5px] leading-relaxed text-pretty")}>
            {profile.bio}
          </p>
        ) : null}

        <Figures
          items={[
            { key: "all", label: t("stats.gamesPlayed"), value: profile.total_games_played },
            { key: "uc", label: t("stats.undercoverPlayed"), value: profile.undercover_games_played },
            { key: "cn", label: t("stats.codenamesPlayed"), value: profile.codenames_games_played },
            { key: "wq", label: t("stats.wordquizPlayed"), value: profile.wordquiz_games_played },
          ]}
        />

        {h2h && h2h.total_games > 0 ? (
          <Panel aria-labelledby="h2h-title">
            <PanelHeader
              title={<span id="h2h-title">{t("stats.headToHead")}</span>}
              sub={t("stats.totalGames", { count: h2h.total_games })}
            />
            <Figures
              framed={false}
              size="md"
              className="-mx-4 grid-cols-3 sm:-mx-[22px]"
              items={[
                { key: "you", label: t("stats.yourWins"), value: h2h.user_wins },
                { key: "them", label: t("stats.theirWins"), value: h2h.opponent_wins },
                { key: "draws", label: t("stats.draws"), value: h2h.draws },
              ]}
            />
          </Panel>
        ) : null}

        {isOwnProfile ? <PlayLinks /> : null}
      </div>
    </div>
  )
}
