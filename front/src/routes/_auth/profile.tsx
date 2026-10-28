import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { KeyRound, Pencil } from "lucide-react"
import { type FormEvent, type KeyboardEvent, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  getPublicProfileApiV1ProfilesUsersUserIdGetQueryKey,
  getUserByIdApiV1UsersUserIdGetQueryKey,
  useDeleteAccountApiV1UsersMeAccountDelete,
  useGetUserByIdApiV1UsersUserIdGet,
  useUpdateUserApiV1UsersUserIdPatch,
  useUpdateUserPasswordApiV1UsersUserIdPasswordPatch,
} from "@/api/generated"
import type { PublicUserView, UserView } from "@/api/generated"
import { currentLanguage } from "@/components/layout/language-switch"
import { countryName, countryOptions } from "@/components/profile/countries"
import { PlayLinks } from "@/components/stats/PlayLinks"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
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

// Backend limits (USERNAME_MIN/MAX_LENGTH, UserUpdate.bio, PASSWORD_MIN_LENGTH)
const USERNAME_MIN = 3
const USERNAME_MAX = 30
const BIO_MAX = 200
const PASSWORD_MIN = 8
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

  const { data: details } = useGetUserByIdApiV1UsersUserIdGet({ user_id: user?.id ?? "" }, { query: { enabled: !!user?.id } }) as {
    data: PublicUserView | undefined
  }

  if (!user) return null

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <div className="mx-auto grid max-w-[72rem] items-start gap-[clamp(20px,2.5vw,32px)] lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="grid min-w-0 gap-[clamp(20px,2.5vw,32px)]">
          <IdentityPanel details={details} editing={editing} setEditing={setEditing} />
          <PlayLinks />
        </div>
        <AccountPanel />
      </div>
    </div>
  )
}

function IdentityPanel({ details, editing, setEditing }: { details: PublicUserView | undefined; editing: Editing; setEditing: (e: Editing) => void }) {
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
            <div className="grid gap-3" aria-hidden="true">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-5/6" />
            </div>
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

/**
 * Escape leaves the form without saving. A key pressed in a portalled layer of the form
 * (the country list) bubbles here through React, but that Escape only closes the list.
 */
function escapeTo(cancel: () => void) {
  return (e: KeyboardEvent<HTMLFormElement>) => {
    if (e.key !== "Escape" || e.defaultPrevented) return
    if (!e.currentTarget.contains(e.target as Node)) return
    e.stopPropagation()
    cancel()
  }
}

function FormActions({ busy, onCancel }: { busy: boolean; onCancel: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap gap-2.5">
      <Button type="submit" size="sm" loading={busy}>
        {t("common.save")}
      </Button>
      <Button variant="secondary" size="sm" onClick={onCancel}>
        {t("common.cancel")}
      </Button>
    </div>
  )
}

function AccountPanel() {
  const { t } = useTranslation()
  const [changing, setChanging] = useState(false)

  return (
    <Panel aria-labelledby="account-title">
      <PanelHeader title={<span id="account-title">{t("profile.account")}</span>} />

      <section aria-labelledby="password-title" className="grid gap-3">
        <h3 id="password-title" className="type-label">
          {t("profile.password")}
        </h3>
        {changing ? (
          <PasswordForm onDone={() => setChanging(false)} />
        ) : (
          <div>
            <Button variant="secondary" size="sm" iconStart={<KeyRound aria-hidden="true" />} onClick={() => setChanging(true)}>
              {t("profile.changePassword")}
            </Button>
          </div>
        )}
      </section>

      <Separator variant="line" className="my-6" />

      <DeleteAccount />
    </Panel>
  )
}

function PasswordForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const changePasswordMutation = useUpdateUserPasswordApiV1UsersUserIdPasswordPatch()
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [errors, setErrors] = useState<{ current?: string; next?: string }>({})

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!user) return
    const found: typeof errors = {}
    if (!currentPassword) found.current = t("profile.currentPasswordRequired")
    // Must match the backend's PASSWORD_MIN_LENGTH (8): the form used to accept 5.
    if (newPassword.length < PASSWORD_MIN) found.next = t("profile.passwordTooShort", { min: PASSWORD_MIN })
    setErrors(found)
    if (found.current || found.next) return
    try {
      await changePasswordMutation.mutateAsync({
        user_id: user.id,
        data: { current_password: currentPassword, new_password: newPassword },
      })
      toast.success(t("profile.passwordChanged"))
      onDone()
    } catch (err) {
      setErrors({ current: getApiErrorMessage(err) })
    }
  }

  return (
    <form onSubmit={submit} onKeyDown={escapeTo(onDone)} className="grid gap-3.5" noValidate>
      <Field label={t("profile.currentPasswordLabel")} error={errors.current}>
        <Input
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          placeholder={t("profile.currentPassword")}
          autoComplete="current-password"
          autoFocus
        />
      </Field>
      <Field label={t("profile.newPasswordLabel")} hint={t("profile.passwordHint", { min: PASSWORD_MIN })} error={errors.next}>
        <Input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder={t("profile.newPassword")}
          autoComplete="new-password"
          minLength={PASSWORD_MIN}
        />
      </Field>
      <FormActions busy={changePasswordMutation.isPending} onCancel={onDone} />
    </form>
  )
}

/** Account deletion: behind a confirmation that asks for the password, as the server does. */
function DeleteAccount() {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const deleteAccountMutation = useDeleteAccountApiV1UsersMeAccountDelete()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)

  const onOpenChange = (next: boolean) => {
    if (deleteAccountMutation.isPending) return
    setOpen(next)
    if (!next) {
      setPassword("")
      setError(null)
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (deleteAccountMutation.isPending) return
    if (!password) {
      setError(t("profile.passwordRequired"))
      return
    }
    try {
      await deleteAccountMutation.mutateAsync({ data: { password } })
      setOpen(false)
      logout()
      navigate({ to: "/" })
      toast.success(t("profile.accountDeleted"))
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }

  return (
    <section aria-labelledby="delete-title" className="grid gap-3">
      <h3 id="delete-title" className="type-label">
        {t("profile.deleteAccount")}
      </h3>
      <p className="text-[14.5px] leading-normal text-muted-foreground text-pretty">{t("profile.deleteAccountDescription")}</p>
      <AlertDialog open={open} onOpenChange={onOpenChange}>
        <AlertDialogTrigger asChild>
          <Button variant="danger" size="sm" className="justify-self-start">
            {t("profile.deleteAccountOpen")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <form onSubmit={submit} className="grid gap-4" noValidate>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("profile.deleteAccountTitle")}</AlertDialogTitle>
              <AlertDialogDescription>{t("profile.deleteAccountWarning")}</AlertDialogDescription>
            </AlertDialogHeader>
            <Field label={t("profile.password")} error={error}>
              <Input
                type="password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  setError(null)
                }}
                placeholder={t("profile.enterPasswordToDelete")}
                autoComplete="current-password"
                autoFocus
              />
            </Field>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleteAccountMutation.isPending}>{t("common.cancel")}</AlertDialogCancel>
              <Button type="submit" variant="danger" loading={deleteAccountMutation.isPending}>
                {t("profile.deleteAccountConfirm")}
              </Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
