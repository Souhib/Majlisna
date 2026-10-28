import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useLoginApiV1AuthLoginPost } from "@/api/generated"
import { AuthPage, authLinkClass } from "@/components/auth/AuthPage"
import { GoogleLoginButton } from "@/components/auth/GoogleLoginButton"
import { PasswordInput } from "@/components/auth/PasswordInput"
import { useFieldErrors } from "@/components/auth/use-field-errors"
import { type AuthField, compactErrors, currentPasswordError, emailError, focusFirstError } from "@/components/auth/validation"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"
import { trackEvent } from "@/lib/analytics"
import { safeRedirect } from "@/lib/redirect"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/auth/login")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: safeRedirect(search.redirect),
  }),
  component: LoginPage,
})

const FIELD_ORDER: AuthField[] = ["email", "password"]

function LoginPage() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const { redirect } = Route.useSearch()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const { errors: fieldErrors, setErrors: setFieldErrors, clear: clearFieldError } = useFieldErrors()

  const loginMutation = useLoginApiV1AuthLoginPost({
    mutation: {
      onSuccess: (d) => {
        trackEvent("login")
        // the server says how long the access token lives; the refresh is scheduled from it
        login(d.access_token, d.refresh_token, d.expires_in, {
          id: d.user.id,
          username: d.user.username,
          email: d.user.email,
        })
        navigate({ href: redirect ?? "/" })
      },
      onError: (err) => {
        setError(getApiErrorMessage(err, t("errors.api.invalidCredentials")))
      },
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setError("")
    const errors = compactErrors({ email: emailError(email), password: currentPasswordError(password) })
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) {
      focusFirstError(errors, FIELD_ORDER)
      return
    }
    loginMutation.mutate({ data: { email, password } })
  }

  return (
    <AuthPage
      title={t("auth.loginTitle")}
      description={t("auth.loginDescription")}
      footer={
        <p>
          {t("auth.noAccount")}{" "}
          <Link to="/auth/register" search={{ redirect }} className={authLinkClass}>
            {t("auth.register")}
          </Link>
        </p>
      }
    >
      {/* the browser's own bubbles speak the browser's language: the fields say it in ours */}
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        {error ? <Alert data-testid="form-error">{error}</Alert> : null}

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

        {/*
          "Forgot password?" sits at the end of the label row but comes AFTER the field in the
          DOM, so Tab goes email → password → forgot. Both share one grid cell, aligned on the
          label's first baseline (the labels are short enough to never meet it, even at 390 px).
        */}
        <div className="grid items-baseline [&>*]:[grid-area:1/1]">
          <Field
            id="password"
            label={t("auth.password")}
            error={fieldErrors.password ? t(fieldErrors.password) : undefined}
          >
            <PasswordInput
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                clearFieldError("password")
              }}
              required
            />
          </Field>
          <Link
            to="/auth/forgot-password"
            className="justify-self-end text-[13px] text-muted-foreground underline decoration-line-brass underline-offset-4 hover:text-foreground hover:decoration-brass pointer-coarse:-my-3 pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center"
          >
            {t("auth.forgotPassword")}
          </Link>
        </div>

        <Button type="submit" block loading={loginMutation.isPending} className="mt-1">
          {t("auth.login")}
        </Button>
      </form>

      <GoogleLoginButton redirectTo={redirect} />
    </AuthPage>
  )
}
