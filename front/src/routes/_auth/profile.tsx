import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Pencil } from "lucide-react"
import { type FormEvent, type ReactNode, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  getPublicProfileApiV1ProfilesUsersUserIdGetQueryKey,
  getUserByIdApiV1UsersUserIdGetQueryKey,
  useGetUserByIdApiV1UsersUserIdGet,
  useUpdateUserApiV1UsersUserIdPatch,
} from "@/api/generated"
import type { PublicUserView, UserView } from "@/api/generated"
import { currentLanguage } from "@/components/layout/language-switch"
import { countryName, countryOptions } from "@/components/profile/countries"
import { ChangePassword } from "@/components/profile/ChangePassword"
import { DeleteAccount } from "@/components/profile/DeleteAccount"
import { escapeTo, FormActions } from "@/components/profile/form-parts"
import { LoadFailed } from "@/components/stats/LoadFailed"
import { PlayLinks } from "@/components/stats/PlayLinks"
import { Avatar } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Field, Input, Textarea } from "@/components/ui/field"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/_auth/profile")({
  component: ProfilePage,
})

// Backend limits (USERNAME_MIN/MAX_LENGTH, UserUpdate.bio)
const USERNAME_MIN = 3
const USERNAME_MAX = 30
const BIO_MAX = 200
const NO_COUNTRY = "none"

type Editing = null | "name" | "details"

/**
 * The player's own profile: who the table sees (name, country, a line about them, the
 * avatar from their Google account when there is one), the doors to the rest of their
 * space, and the account (password, deletion). Edits happen in place, one form at a time.
 */
function ProfilePage() {
  const { user } = useAuth()
  const [editing, setEditing] = useState<Editing>(null)

  const detailsQuery = useGetUserByIdApiV1UsersUserIdGet({ user_id: user?.id ?? "" }, { query: { enabled: !!user?.id } })
  const details: PublicUserView | undefined = detailsQuery.data

  if (!user) return null

  // a failed read of the details is said, with Retry: it used to be a skeleton that never ended (FR-7)
  const detailsFailed = detailsQuery.isError ? (
    <LoadFailed error={detailsQuery.error} retrying={detailsQuery.isRefetching} onRetry={() => void detailsQuery.refetch()} />
  ) : null

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <div className="mx-auto grid max-w-[72rem] items-start gap-[clamp(20px,2.5vw,32px)] lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="grid min-w-0 gap-[clamp(20px,2.5vw,32px)]">
          <IdentityPanel details={details} failed={detailsFailed} editing={editing} setEditing={setEditing} />
          <PlayLinks />
        </div>
        <AccountPanel />
      </div>
    </div>
  )
}

function IdentityPanel({
  details,
  failed,
  editing,
  setEditing,
}: {
  details: PublicUserView | undefined
  /** What to show instead of the details when their read failed. */
  failed: ReactNode
  editing: Editing
  setEditing: (e: Editing) => void
}) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  if (!user) return null
  const country = countryName(details?.country, i18n.language)
  // the bio keeps its own direction (dir="auto") but lines up with the page
  const pageAlign = currentLanguage(i18n.language) === "ar" ? "text-right" : "text-left"

  return (
    <Panel aria-labelledby="profile-name">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <Avatar name={user.username} src={details?.profile_picture_url} size={72} decorative />
        <div className="grid min-w-0 flex-1 basis-48 gap-1">
          <div className="flex min-w-0 items-center gap-1">
            {/* the display role, like every page title and the lobby's "Yusuf’s majlis": its
                figures are Readex (Samar Figures, first in the stack), and an Arabic name
                falls to Amiri */}
            <h1 id="profile-name" dir="auto" className="type-title min-w-0 break-words text-[clamp(28px,2.6vw,40px)] leading-[1.15]">
              {user.username}
            </h1>
            {editing === "name" ? null : (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("profile.editUsername")}
                onClick={() => setEditing("name")}
                className="shrink-0 text-muted-foreground hover:text-foreground"
              >
                <Pencil aria-hidden="true" />
              </Button>
            )}
          </div>
          {user.email ? (
            <p className="text-[14.5px] text-muted-foreground">
              <span dir="ltr" className="bidi-isolate break-all">
                {user.email}
              </span>
            </p>
          ) : null}
        </div>
      </div>

      {editing === "name" ? <UsernameForm onDone={() => setEditing(null)} /> : null}

      <Separator variant="line" className="my-5" />

      {editing === "details" ? (
        <DetailsForm details={details} onDone={() => setEditing(null)} />
      ) : (
        <div className="grid gap-4">
          {details ? (
            <dl className="grid gap-3 text-[15.5px] sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-x-6">
              <dt className="type-label pt-0.5">{t("profile.country")}</dt>
              <dd className={country ? "" : "text-muted-foreground"}>{country ?? t("profile.noCountry")}</dd>
              <dt className="type-label pt-0.5">{t("profile.bio")}</dt>
              <dd dir="auto" className={cn(pageAlign, details.bio ? "leading-relaxed text-pretty" : "text-muted-foreground")}>
                {details.bio || t("profile.noBio")}
              </dd>
            </dl>
          ) : (
            (failed ?? (
              <div className="grid gap-3" aria-hidden="true">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-5 w-5/6" />
              </div>
            ))
          )}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            {/* the form starts from the saved values, so it opens once they are here */}
            <Button variant="secondary" size="sm" iconStart={<Pencil aria-hidden="true" />} disabled={!details} onClick={() => setEditing("details")}>
              {t("profile.editDetails")}
            </Button>
            <Button asChild variant="link" size="sm" className="pointer-coarse:min-h-11">
              <Link to="/players/$userId" params={{ userId: user.id }}>
                {t("profile.publicPage")}
              </Link>
            </Button>
          </div>
        </div>
      )}
    </Panel>
  )
}

/** Keep the session's copy of the user in step with the server's. */
function useApplyUserUpdate() {
  const { setUser } = useAuth()
  const queryClient = useQueryClient()
  return (updated: UserView) => {
    // setUser also persists the session's copy (AuthProvider.setUserData)
    setUser({ id: updated.id, username: updated.username ?? "", email: updated.email_address })
    queryClient.invalidateQueries({ queryKey: getUserByIdApiV1UsersUserIdGetQueryKey({ user_id: updated.id }) })
    queryClient.invalidateQueries({ queryKey: getPublicProfileApiV1ProfilesUsersUserIdGetQueryKey({ user_id: updated.id }) })
  }
}

function UsernameForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const apply = useApplyUserUpdate()
  const updateUserMutation = useUpdateUserApiV1UsersUserIdPatch()
  const [value, setValue] = useState(user?.username ?? "")
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!user) return
    const next = value.trim()
    if (next === user.username) return onDone()
    if (next.length < USERNAME_MIN || next.length > USERNAME_MAX) {
      setError(t("profile.usernameLength", { min: USERNAME_MIN, max: USERNAME_MAX }))
      return
    }
    try {
      const updated = (await updateUserMutation.mutateAsync({ user_id: user.id, data: { username: next } })) as UserView
      apply(updated)
      toast.success(t("profile.saved"))
      onDone()
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} onKeyDown={escapeTo(onDone)} className="mt-5 grid gap-3" noValidate>
      <Field label={t("profile.username")} hint={t("profile.usernameHint", { min: USERNAME_MIN, max: USERNAME_MAX })} error={error}>
        <Input
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setError(null)
          }}
          maxLength={USERNAME_MAX}
          autoComplete="username"
          autoFocus
        />
      </Field>
      <FormActions busy={updateUserMutation.isPending} onCancel={onDone} />
    </form>
  )
}

function DetailsForm({ details, onDone }: { details: PublicUserView | undefined; onDone: () => void }) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const apply = useApplyUserUpdate()
  const updateUserMutation = useUpdateUserApiV1UsersUserIdPatch()
  const [country, setCountry] = useState(details?.country?.toUpperCase() ?? NO_COUNTRY)
  const [bio, setBio] = useState(details?.bio ?? "")
  const [error, setError] = useState<string | null>(null)
  const options = useMemo(() => countryOptions(i18n.language), [i18n.language])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!user) return
    try {
      const updated = (await updateUserMutation.mutateAsync({
        user_id: user.id,
        data: { country: country === NO_COUNTRY ? null : country, bio: bio.trim() || null },
      })) as UserView
      apply(updated)
      toast.success(t("profile.saved"))
      onDone()
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} onKeyDown={escapeTo(onDone)} className="grid gap-4" noValidate>
      <Field id="profile-country" label={t("profile.country")} hint={t("profile.countryHint")}>
        <Select value={country} onValueChange={setCountry}>
          <SelectTrigger id="profile-country" autoFocus>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_COUNTRY}>{t("profile.noCountry")}</SelectItem>
            <SelectSeparator />
            {options.map((o) => (
              <SelectItem key={o.code} value={o.code}>
                {o.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field
        label={t("profile.bio")}
        hint={t("profile.bioHint", { max: BIO_MAX })}
        error={error}
        labelEnd={
          <span className="type-meta num" dir="ltr" aria-hidden="true">
            {bio.length} / {BIO_MAX}
          </span>
        }
      >
        <Textarea
          dir="auto"
          value={bio}
          onChange={(e) => {
            setBio(e.target.value)
            setError(null)
          }}
          maxLength={BIO_MAX}
          rows={3}
        />
      </Field>
      <FormActions busy={updateUserMutation.isPending} onCancel={onDone} />
    </form>
  )
}

function AccountPanel() {
  const { t } = useTranslation()

  return (
    <Panel aria-labelledby="account-title">
      <PanelHeader title={<span id="account-title">{t("profile.account")}</span>} />

      <ChangePassword />

      <Separator variant="line" className="my-6" />

      <DeleteAccount />
    </Panel>
  )
}
