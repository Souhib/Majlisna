import { useGoogleLogin, useGoogleOAuth } from "@react-oauth/google"
import { useNavigate } from "@tanstack/react-router"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { type DeleteAccountRequest, useDeleteAccountApiV1UsersMeAccountDelete, useGetMeApiV1AuthMeGet } from "@/api/generated"
import { GoogleIcon, googleClientId, WithGoogleOAuth } from "@/components/auth/GoogleLoginButton"
import { passwordErrorMessage } from "@/components/profile/password-error"
import { LoadFailed } from "@/components/stats/LoadFailed"
import { Alert } from "@/components/ui/alert"
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
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/providers/AuthProvider"

/** `UserView.auth_provider` of an account opened with "Continue with Google" (the backend's AUTH_PROVIDER_GOOGLE). */
const GOOGLE_PROVIDER = "google"

/** Google's window closed by the player: their own choice, not an error to say. */
const GOOGLE_POPUP_CLOSED = "popup_closed"

/**
 * Account deletion, behind the confirmation the server asks for (SEC F14):
 *
 * - an account with a password confirms with it;
 * - a Google account (`auth_provider` "google", whose password is a random value its owner
 *   never saw) confirms with Google: "Confirm with Google" asks Google for a fresh access
 *   token for that address, and the server checks that the token's account is this one
 *   (`errors.api.googleAccountMismatch` otherwise). Google's provider is mounted inside the
 *   open dialog only, so its script loads when the dialog opens and goes when it closes.
 *
 * Which of the two is read from `/auth/me` when the dialog opens. A build without
 * `VITE_GOOGLE_CLIENT_ID` has no Google: it falls back to the password (a Google account
 * can set one through "Forgot password?").
 */
export function DeleteAccount() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const deleteAccountMutation = useDeleteAccountApiV1UsersMeAccountDelete()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  // read once the dialog is open: the page itself never needs it
  const me = useGetMeApiV1AuthMeGet({ query: { enabled: open && !!user } })
  const withGoogle = me.data?.auth_provider === GOOGLE_PROVIDER && !!googleClientId()
  const busy = deleteAccountMutation.isPending

  const onOpenChange = (next: boolean) => {
    if (busy) return
    setOpen(next)
    if (!next) {
      setPassword("")
      setError(null)
    }
  }

  const deleteWith = async (data: DeleteAccountRequest) => {
    if (busy) return
    setError(null)
    try {
      await deleteAccountMutation.mutateAsync({ data })
      setOpen(false)
      logout()
      navigate({ to: "/" })
      toast.success(t("profile.accountDeleted"))
    } catch (err) {
      setError(passwordErrorMessage(err, t))
    }
  }

  const submitPassword = (e: FormEvent) => {
    e.preventDefault()
    if (!password) {
      setError(t("profile.passwordRequired"))
      return
    }
    void deleteWith({ password })
  }

  const confirmation = me.isError ? (
    <LoadFailed error={me.error} retrying={me.isRefetching} onRetry={() => void me.refetch()} />
  ) : !me.data ? (
    <div className="grid gap-3" aria-hidden="true">
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-11 w-full" />
    </div>
  ) : withGoogle ? (
    error ? (
      <Alert tone="error">{error}</Alert>
    ) : null
  ) : (
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
  )

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
          <form onSubmit={submitPassword} className="grid gap-4" noValidate>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("profile.deleteAccountTitle")}</AlertDialogTitle>
              <AlertDialogDescription>{t(withGoogle ? "profile.deleteAccountWarningGoogle" : "profile.deleteAccountWarning")}</AlertDialogDescription>
            </AlertDialogHeader>
            {confirmation}
            <AlertDialogFooter>
              <AlertDialogCancel disabled={busy}>{t("common.cancel")}</AlertDialogCancel>
              {withGoogle ? (
                <WithGoogleOAuth onScriptLoadError={() => setError(t("profile.deleteAccountGoogleFailed"))}>
                  <ConfirmWithGoogle
                    email={me.data?.email_address}
                    busy={busy}
                    onToken={(token) => void deleteWith({ google_access_token: token })}
                    onRefused={() => setError(t("profile.deleteAccountGoogleFailed"))}
                    onAsk={() => setError(null)}
                  />
                </WithGoogleOAuth>
              ) : me.data ? (
                <Button type="submit" variant="danger" loading={busy}>
                  {t("profile.deleteAccountConfirm")}
                </Button>
              ) : null}
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}

/**
 * "Confirm with Google": asks Google for a fresh access token for the account's address
 * (`hint`), with the account chooser shown (`prompt: "select_account"`): an irreversible
 * act is confirmed by a choice the player makes, never by a silent token. Busy until
 * Google's script is there. Lives under `WithGoogleOAuth` (its hooks need the provider).
 */
function ConfirmWithGoogle({
  email,
  busy,
  onToken,
  onRefused,
  onAsk,
}: {
  email?: string
  busy: boolean
  onToken: (accessToken: string) => void
  onRefused: () => void
  onAsk: () => void
}) {
  const { t } = useTranslation()
  const { scriptLoadedSuccessfully } = useGoogleOAuth()
  const askGoogle = useGoogleLogin({
    hint: email,
    prompt: "select_account",
    onSuccess: (response) => onToken(response.access_token),
    onError: () => onRefused(),
    onNonOAuthError: (nonOAuthError) => {
      if (nonOAuthError.type !== GOOGLE_POPUP_CLOSED) onRefused()
    },
  })
  return (
    <Button
      variant="danger"
      loading={busy || !scriptLoadedSuccessfully}
      iconStart={<GoogleIcon />}
      onClick={() => {
        onAsk()
        askGoogle()
      }}
    >
      {t("profile.deleteAccountConfirmWithGoogle")}
    </Button>
  )
}
