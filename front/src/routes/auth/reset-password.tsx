import { createFileRoute, Link, useSearch } from "@tanstack/react-router"
import { ArrowLeft, ArrowRight } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useResetPasswordApiV1AuthResetPasswordPost } from "@/api/generated"
import { AuthPage, authLinkClass } from "@/components/auth/AuthPage"
import { PasswordInput } from "@/components/auth/PasswordInput"
import { useFieldErrors } from "@/components/auth/use-field-errors"
import {
  apiErrorKey,
  type AuthField,
  compactErrors,
  confirmError,
  focusFirstError,
  newPasswordError,
  PASSWORD_MIN_LENGTH,
  TOKEN_REJECTED_KEY,
} from "@/components/auth/validation"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field } from "@/components/ui/field"

export const Route = createFileRoute("/auth/reset-password")({
  component: ResetPasswordPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || "",
  }),
})

const FIELD_ORDER: AuthField[] = ["password", "confirmPassword"]

function BackToLogin() {
  const { t } = useTranslation()
  return (
    <Link to="/auth/login" className={`${authLinkClass} gap-2`}>
      <ArrowLeft className="size-4 rtl-flip" aria-hidden="true" />
      {t("auth.backToLogin")}
    </Link>
  )
}

function ResetPasswordPage() {
  const { t } = useTranslation()
  const { token } = useSearch({ from: "/auth/reset-password" })
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const { errors: fieldErrors, setErrors: setFieldErrors, clear: clearFieldError } = useFieldErrors()

  const resetMutation = useResetPasswordApiV1AuthResetPasswordPost({
    mutation: {
      onSuccess: () => setSuccess(true),
      // a refused link is said in the page's language (the server's key has no translation)
      onError: (err) => setError(apiErrorKey(err) === TOKEN_REJECTED_KEY ? t("auth.invalidOrExpiredToken") : getApiErrorMessage(err, t("common.error"))),
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setError("")
    // The server requires 8 characters (PASSWORD_MIN_LENGTH). This page used to accept
    // 5 and say so, then fail on the server with a message in English.
    const errors = compactErrors({
      password: newPasswordError(password),
      confirmPassword: newPasswordError(password) ? undefined : confirmError(password, confirmPassword),
    })
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) {
      focusFirstError(errors, FIELD_ORDER)
      return
    }
    resetMutation.mutate({ data: { token, new_password: password } })
  }

  if (!token) {
    return (
      <AuthPage title={t("auth.resetPassword")} footer={<BackToLogin />}>
        <div className="grid gap-5">
          <Alert>
            <p>{t("auth.invalidOrExpiredToken")}</p>
            <p className="mt-1 text-muted-foreground">{t("auth.linkExpiredHelp")}</p>
          </Alert>
          <Button asChild block iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
            <Link to="/auth/forgot-password">{t("auth.requestNewLink")}</Link>
          </Button>
        </div>
      </AuthPage>
    )
  }

  if (success) {
    return (
      <AuthPage title={t("auth.resetPassword")}>
        <div className="grid gap-5">
          <Alert tone="info">{t("auth.passwordResetSuccess")}</Alert>
          <Button asChild block iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
            <Link to="/auth/login">{t("auth.login")}</Link>
          </Button>
        </div>
      </AuthPage>
    )
  }

  return (
    <AuthPage title={t("auth.resetPassword")} description={t("auth.resetPasswordDescription")} footer={<BackToLogin />}>
      <form onSubmit={handleSubmit} noValidate className="grid gap-5">
        {error ? (
          <Alert data-testid="form-error">
            <p>{error}</p>
            <Link to="/auth/forgot-password" className={`${authLinkClass} mt-1`}>
              {t("auth.requestNewLink")}
            </Link>
          </Alert>
        ) : null}
        <Field id="password" label={t("auth.newPassword")} hint={t("auth.passwordHint")} error={fieldErrors.password ? t(fieldErrors.password) : undefined}>
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
        <Field id="confirmPassword" label={t("auth.confirmPassword")} error={fieldErrors.confirmPassword ? t(fieldErrors.confirmPassword) : undefined}>
          <PasswordInput
            autoComplete="new-password"
            minLength={PASSWORD_MIN_LENGTH}
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value)
              clearFieldError("confirmPassword")
            }}
            required
          />
        </Field>
        <Button type="submit" block loading={resetMutation.isPending} className="mt-1">
          {t("auth.saveNewPassword")}
        </Button>
      </form>
    </AuthPage>
  )
}
