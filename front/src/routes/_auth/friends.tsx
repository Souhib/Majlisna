import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Check, Search } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { queryKeys } from "@/api/queryKeys"
import {
  useAcceptFriendRequestApiV1FriendsFriendshipIdAcceptPost,
  useGetFriendsApiV1FriendsGet,
  useGetPendingRequestsApiV1FriendsPendingGet,
  useRejectFriendRequestApiV1FriendsFriendshipIdRejectPost,
  useRemoveFriendApiV1FriendsFriendshipIdDelete,
} from "@/api/generated"
import type { FriendEntry } from "@/api/generated"
import { FriendRow } from "@/components/friends/FriendRow"
import { RemoveFriendButton } from "@/components/friends/RemoveFriendButton"
import { PageHeader, Segmented } from "@/components/stats/PlayerSpace"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/chip"
import { EmptyState } from "@/components/ui/empty-state"
import { Field, Input } from "@/components/ui/field"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/providers/AuthProvider"

type Tab = "friends" | "pending"

export const Route = createFileRoute("/_auth/friends")({
  component: FriendsPage,
})

/**
 * Friends: the accepted list (searchable) and the requests sent to you. A friendship
 * starts from a player's page (there is no people search on the server by design), so
 * the page says where to go and links there.
 */
function FriendsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>("friends")
  const [searchQuery, setSearchQuery] = useState("")

  const { data: friends = [], isLoading: friendsLoading } = useGetFriendsApiV1FriendsGet({ query: { enabled: !!user } }) as {
    data: FriendEntry[] | undefined
    isLoading: boolean
  }
  const { data: pending = [], isLoading: pendingLoading } = useGetPendingRequestsApiV1FriendsPendingGet({
    query: { enabled: !!user },
  }) as { data: FriendEntry[] | undefined; isLoading: boolean }

  const isLoading = friendsLoading || pendingLoading
  const queryClient = useQueryClient()

  const invalidateFriendQueries = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.friends.list() })
    queryClient.invalidateQueries({ queryKey: queryKeys.friends.pending() })
  }

  const acceptMutation = useAcceptFriendRequestApiV1FriendsFriendshipIdAcceptPost({
    mutation: {
      onSuccess: () => {
        toast.success(t("friends.requestAccepted"))
        invalidateFriendQueries()
      },
      onError: (err) => toast.error(getApiErrorMessage(err)),
    },
  })
  const rejectMutation = useRejectFriendRequestApiV1FriendsFriendshipIdRejectPost({
    mutation: {
      onSuccess: () => {
        toast.success(t("friends.requestRejected"))
        invalidateFriendQueries()
      },
      onError: (err) => toast.error(getApiErrorMessage(err)),
    },
  })
  const removeMutation = useRemoveFriendApiV1FriendsFriendshipIdDelete({
    mutation: {
      onSuccess: () => {
        toast.success(t("friends.friendRemoved"))
        invalidateFriendQueries()
      },
      onError: (err) => toast.error(getApiErrorMessage(err)),
    },
  })

  const busyFor = (m: { isPending: boolean; variables?: { friendship_id: string } }, id: string) => m.isPending && m.variables?.friendship_id === id

  const query = searchQuery.trim().toLowerCase()
  const filteredFriends = friends.filter((f) => f.username.toLowerCase().includes(query))

  const findPlayers = (
    <Button asChild variant="secondary">
      <Link to="/leaderboard">{t("friends.findPlayers")}</Link>
    </Button>
  )

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <div className="mx-auto max-w-[46rem]">
        <PageHeader title={t("friends.title")} lede={t("friends.howToAdd")} />

        <Segmented<Tab>
          label={t("friends.title")}
          value={tab}
          onChange={setTab}
          className="mb-5 w-full sm:w-fit sm:min-w-[24rem]"
          options={[
            {
              value: "friends",
              label: t("friends.myFriends"),
              badge: <Badge>{friends.length}</Badge>,
            },
            {
              value: "pending",
              label: t("friends.pendingRequests"),
              badge: <Badge tone={pending.length > 0 ? "brass" : "neutral"}>{pending.length}</Badge>,
            },
          ]}
        />

        {tab === "friends" ? (
          <>
            {friends.length > 0 ? (
              <Field label={t("friends.searchLabel")} hideLabel className="mb-4">
                <div className="relative">
                  <Search className="pointer-events-none absolute start-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                  <Input
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t("friends.searchPlaceholder")}
                    className="ps-10"
                  />
                </div>
              </Field>
            ) : null}
            <Panel flush>
              {isLoading ? (
                <ListSkeleton />
              ) : friends.length === 0 ? (
                <EmptyState titleAs="h2" title={t("friends.noFriends")} description={t("friends.noFriendsBody")} action={findPlayers} />
              ) : filteredFriends.length === 0 ? (
                <p className="px-4 py-10 text-center text-muted-foreground" role="status">
                  {t("friends.noResults")}
                </p>
              ) : (
                <ul aria-label={t("friends.myFriends")}>
                  {filteredFriends.map((friend) => (
                    <FriendRow
                      key={friend.friendship_id}
                      userId={friend.user_id}
                      username={friend.username}
                      actions={
                        <RemoveFriendButton
                          compact
                          name={friend.username}
                          busy={busyFor(removeMutation, friend.friendship_id)}
                          onConfirm={() => removeMutation.mutate({ friendship_id: friend.friendship_id })}
                        />
                      }
                    />
                  ))}
                </ul>
              )}
            </Panel>
          </>
        ) : (
          <Panel flush>
            {isLoading ? (
              <ListSkeleton />
            ) : pending.length === 0 ? (
              <EmptyState titleAs="h2" title={t("friends.noPending")} description={t("friends.noPendingBody")} action={findPlayers} />
            ) : (
              <ul aria-label={t("friends.pendingRequests")}>
                {pending.map((request) => (
                  <FriendRow
                    key={request.friendship_id}
                    userId={request.user_id}
                    username={request.username}
                    sub={t("friends.wantsToBeFriends")}
                    actions={
                      <>
                        <Button
                          size="sm"
                          iconStart={<Check aria-hidden="true" />}
                          loading={busyFor(acceptMutation, request.friendship_id)}
                          disabled={busyFor(rejectMutation, request.friendship_id)}
                          onClick={() => acceptMutation.mutate({ friendship_id: request.friendship_id })}
                          aria-label={t("friends.acceptNamed", { name: request.username })}
                        >
                          {t("friends.accept")}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={busyFor(rejectMutation, request.friendship_id)}
                          disabled={busyFor(acceptMutation, request.friendship_id)}
                          onClick={() => rejectMutation.mutate({ friendship_id: request.friendship_id })}
                          aria-label={t("friends.rejectNamed", { name: request.username })}
                        >
                          {t("friends.reject")}
                        </Button>
                      </>
                    }
                  />
                ))}
              </ul>
            )}
          </Panel>
        )}
      </div>
    </div>
  )
}

function ListSkeleton() {
  return (
    <div className="grid gap-3 p-4 sm:p-[22px]" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <Skeleton className="h-4 w-40" />
        </div>
      ))}
    </div>
  )
}
