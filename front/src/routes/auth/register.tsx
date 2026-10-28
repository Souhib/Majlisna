import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useLoginApiV1AuthLoginPost, useRegisterApiV1AuthRegisterPost } from "@/api/generated"
import { AuthPage, authLinkClass } from "@/components/auth/AuthPage"
import { GoogleLoginButton } from "@/components/auth/GoogleLoginButton"
import { PasswordInput } from "@/components/auth/PasswordInput"
import { useFieldErrors } from "@/components/auth/use-field-errors"
import {
  type AuthField,
  compactErrors,
  emailError,
  focusFirstError,
  newPasswordError,
  PASSWORD_MIN_LENGTH,
  usernameError,
} from "@/components/auth/validation"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"
import { trackEvent } from "@/lib/analytics"
import { safeRedirect } from "@/lib/redirect"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/auth/register")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: safeRedirect(search.redirect),
  }),
  component: RegisterPage,
})

const FIELD_ORDER: AuthField[] = ["username", "email", "password"]

function RegisterPage() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const { redirect } = Route.useSearch()
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  /** Registered, but the automatic log-in did not go through (e.g. email to verify first). */
  const [createdNotice, setCreatedNotice] = useState<string | null>(null)
  const { errors: fieldErrors, setErrors: setFieldErrors, clear: clearFieldError } = useFieldErrors()

  const registerMutation = useRegisterApiV1AuthRegisterPost()
  const loginMutation = useLoginApiV1AuthLoginPost()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setCreatedNotice(null)
    const errors = compactErrors({
      username: usernameError(username),
      email: emailError(email),
      password: newPasswordError(password),
    })
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) {
      focusFirstError(errors, FIELD_ORDER)
      return
    }

    try {
      await registerMutation.mutateAsync({ data: { username, email_address: email, password } })
    } catch (err) {
      setError(getApiErrorMessage(err, t("errors.api.userAlreadyExists")))
      return
    }
    trackEvent("signup")

    // POST /auth/register answers with the new user only (a UserView), never tokens.
    // This page used to hand that response to login(), which stored the string
    // "undefined" as the token: the player looked signed in and the next request 401'd.
    // Logging in with the credentials just chosen is what actually opens the session.
    try {
      const session = await loginMutation.mutateAsync({ data: { email, password } })
      login(session.access_token, session.refresh_token, session.expires_in, {
        id: session.user.id,
        username: session.user.username,
        email: session.user.email,
      })
      navigate({ href: redirect ?? "/" })
    } catch (err) {
      setCreatedNotice(getApiErrorMessage(err, ""))
    }
  }

  const busy = registerMutation.isPending || loginMutation.isPending

  return (
    <AuthPage
      title={t("auth.registerTitle")}
      description={t("auth.registerDescription")}
      footer={
        <p>
          {t("auth.hasAccount")}{" "}
          <Link to="/auth/login" search={{ redirect }} className={authLinkClass}>
            {t("auth.login")}
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        {error ? <Alert data-testid="form-error">{error}</Alert> : null}
        {createdNotice !== null ? (
          <Alert tone="info">
            <p>{t("auth.accountCreated")}</p>
            {createdNotice ? <p className="mt-1 text-muted-foreground">{createdNotice}</p> : null}
            <Link to="/auth/login" search={{ redirect }} className={`${authLinkClass} mt-2`}>
              {t("auth.login")}
            </Link>
          </Alert>
        ) : null}

        <Field
          id="username"
          label={t("auth.username")}
          hint={t("auth.usernameHint")}
          error={fieldErrors.username ? t(fieldErrors.username) : undefined}
        >
          <Input
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(e) => {
              setUsername(e.target.value)
              clearFieldError("username")
            }}
            required
          />
        </Field>

        <Field id="email" label={t("auth.email")} error={fieldErrors.email ? t(fieldErrors.email) : undefined}>
          <Input
            type="email"
            autoComplete="email"
            inputMode="email"
            autoCapitalize="none"
            spellCheck={false}
            dir="ltr"
            className="rtl:text-right"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              clearFieldError("email")
            }}
            required
          />
        </Field>

        <Field
          id="password"
          label={t("auth.password")}
          hint={t("auth.passwordHint")}
          error={fieldErrors.password ? t(fieldErrors.password) : undefined}
        >
          <PasswordInput
            autoComplete="new-password"
            minLength={PASSWORD_MIN_LENGTH}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              clearFieldError("password")
            }}
            required
          />
        </Field>

        <Button type="submit" block loading={busy} className="mt-1">
          {t("auth.register")}
        </Button>
      </form>

      <GoogleLoginButton redirectTo={redirect} />
    </AuthPage>
  )
}
