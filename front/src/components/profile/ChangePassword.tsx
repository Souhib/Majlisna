import { useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { KeyRound } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  getMeApiV1AuthMeGetQueryKey,
  type UserUpdatePassword,
  type UserView,
  useGetMeApiV1AuthMeGet,
  useUpdateUserPasswordApiV1UsersUserIdPasswordPatch,
} from "@/api/generated"
import { GoogleIcon, googleClientId, WithGoogleOAuth } from "@/components/auth/GoogleLoginButton"
import { escapeTo, FormActions } from "@/components/profile/form-parts"
import { passwordErrorMessage } from "@/components/profile/password-error"
import { GOOGLE_PROVIDER, useGoogleConfirmation } from "@/components/profile/use-google-confirmation"
import { LoadFailed } from "@/components/stats/LoadFailed"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/providers/AuthProvider"

/** Must match the backend's PASSWORD_MIN_LENGTH (8): the form used to accept 5. */
const PASSWORD_MIN = 8

/** What a password form says: under the current or the new password, or about the confirmation. */
type Errors = { current?: string; next?: string; confirm?: string }

/**
 * "Change password", for every account (profile → Account):
 *
 * - an account with a password confirms the change with its current password;
 * - a Google-only account (`auth_provider` "google", whose stored password is a random value
 *   its owner never saw) chooses one and confirms with Google; the server then lets that
 *   password open the account at sign-in, and Google sign-in still does. Google's provider is
 *   mounted inside the open form only, so its script loads when it opens and goes when it
 *   closes (as account deletion does). A build without `VITE_GOOGLE_CLIENT_ID` offers the
 *   emailed reset link instead.
 *
 * Which of the two is read from `/auth/me` once "Change password" is pressed; the answer to
 * the change is the account, written back into that query, so the form and the deletion
 * dialog ask for the new password from then on.
 */
export function ChangePassword() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <section aria-labelledby="password-title" className="grid gap-3">
      <h3 id="password-title" className="type-label">
        {t("profile.password")}
      </h3>
      {open ? (
        <PasswordForms onDone={() => setOpen(false)} />
      ) : (
        <div>
          <Button variant="secondary" size="sm" iconStart={<KeyRound aria-hidden="true" />} onClick={() => setOpen(true)}>
            {t("profile.changePassword")}
          </Button>
        </div>
      )}
    </section>
  )
}

function PasswordForms({ onDone }: { onDone: () => void }) {
  const { user } = useAuth()
  const me = useGetMeApiV1AuthMeGet({ query: { enabled: !!user } })
  const [googleScriptFailed, setGoogleScriptFailed] = useState(false)

  if (me.isError) return <LoadFailed error={me.error} retrying={me.isRefetching} onRetry={() => void me.refetch()} />
  if (!me.data) {
    return (
      <div className="grid gap-3" aria-hidden="true">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-11 w-full" />
      </div>
    )
  }
  if (me.data.auth_provider !== GOOGLE_PROVIDER) return <CurrentPasswordForm onDone={onDone} />
  if (!googleClientId()) return <SetPasswordByEmail onDone={onDone} />
  return (
    <WithGoogleOAuth onScriptLoadError={() => setGoogleScriptFailed(true)}>
      <GooglePasswordForm email={me.data.email_address} scriptFailed={googleScriptFailed} onDone={onDone} />
    </WithGoogleOAuth>
  )
}

/** Sends the change; on success the account answered is the new `/auth/me`, and the page says so. */
function useSavePassword(onDone: () => void) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const mutation = useUpdateUserPasswordApiV1UsersUserIdPasswordPatch()

  const save = async (data: UserUpdatePassword, said: string) => {
    if (!user) return
    const updated = (await mutation.mutateAsync({ user_id: user.id, data })) as UserView
    // a Google-only account has a password now: what reads /auth/me asks for it from here on
    queryClient.setQueryData(getMeApiV1AuthMeGetQueryKey(), updated)
    toast.success(said)
    onDone()
  }
  return { save, busy: mutation.isPending }
}

function CurrentPasswordForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  const { save, busy } = useSavePassword(onDone)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [errors, setErrors] = useState<Errors>({})

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const found: Errors = {}
    if (!currentPassword) found.current = t("profile.currentPasswordRequired")
    if (newPassword.length < PASSWORD_MIN) found.next = t("profile.passwordTooShort", { min: PASSWORD_MIN })
    setErrors(found)
    if (found.current || found.next) return
    try {
      await save({ current_password: currentPassword, new_password: newPassword }, t("profile.passwordChanged"))
    } catch (err) {
      // a wrong current password is the login's 401: said as a wrong password (F6)
      setErrors({ current: passwordErrorMessage(err, t) })
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
      <NewPasswordField value={newPassword} onChange={setNewPassword} error={errors.next} />
      <FormActions busy={busy} onCancel={onDone} />
    </form>
  )
}

/**
 * A Google-only account: the new password, then "Confirm with Google" (the form's submit,
 * so Enter does the same). The password is checked before Google is asked.
 */
function GooglePasswordForm({ email, scriptFailed, onDone }: { email: string; scriptFailed: boolean; onDone: () => void }) {
  const { t } = useTranslation()
  const { save, busy } = useSavePassword(onDone)
  const [newPassword, setNewPassword] = useState("")
  const [errors, setErrors] = useState<Errors>({})
  const google = useGoogleConfirmation({
    email,
    onToken: (token) => {
      save({ google_access_token: token, new_password: newPassword }, t("profile.passwordSet")).catch((err: unknown) =>
        setErrors({ confirm: passwordErrorMessage(err, t) }),
      )
    },
    onRefused: () => setErrors({ confirm: t("profile.passwordGoogleFailed") }),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (busy || !google.ready) return
    if (newPassword.length < PASSWORD_MIN) {
      setErrors({ next: t("profile.passwordTooShort", { min: PASSWORD_MIN }) })
      return
    }
    setErrors({})
    google.ask()
  }

  const refusal = errors.confirm ?? (scriptFailed ? t("profile.passwordGoogleFailed") : null)

  return (
    <form onSubmit={submit} onKeyDown={escapeTo(onDone)} className="grid gap-3.5" noValidate>
      <p className="text-[14.5px] leading-normal text-muted-foreground text-pretty">{t("profile.passwordGoogleIntro")}</p>
      <NewPasswordField value={newPassword} onChange={setNewPassword} error={errors.next} autoFocus />
      {refusal ? <Alert tone="error">{refusal}</Alert> : null}
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit" size="sm" loading={busy || !google.ready} iconStart={<GoogleIcon />}>
          {t("profile.passwordConfirmWithGoogle")}
        </Button>
        <Button variant="secondary" size="sm" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  )
}

/** A build without Google: a Google-only account sets its password through the emailed reset link. */
function SetPasswordByEmail({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-3.5">
      <p className="text-[14.5px] leading-normal text-muted-foreground text-pretty">{t("profile.passwordSetByEmail")}</p>
      <div className="flex flex-wrap gap-2.5">
        <Button asChild size="sm">
          <Link to="/auth/forgot-password">{t("profile.passwordSetByEmailLink")}</Link>
        </Button>
        <Button variant="secondary" size="sm" onClick={onDone}>
          {t("common.cancel")}
        </Button>
      </div>
    </div>
  )
}

function NewPasswordField({ value, onChange, error, autoFocus }: { value: string; onChange: (value: string) => void; error?: string; autoFocus?: boolean }) {
  const { t } = useTranslation()
  return (
    <Field label={t("profile.newPasswordLabel")} hint={t("profile.passwordHint", { min: PASSWORD_MIN })} error={error}>
      <Input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("profile.newPassword")}
        autoComplete="new-password"
        minLength={PASSWORD_MIN}
        autoFocus={autoFocus}
      />
    </Field>
  )
}
