import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useForgotPasswordApiV1AuthForgotPasswordPost } from "@/api/generated"
import { AuthPage, authLinkClass } from "@/components/auth/AuthPage"
import { useFieldErrors } from "@/components/auth/use-field-errors"
import { compactErrors, emailError, focusFirstError } from "@/components/auth/validation"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"

export const Route = createFileRoute("/auth/forgot-password")({
  component: ForgotPasswordPage,
})

function BackToLogin() {
  const { t } = useTranslation()
  return (
    <Link to="/auth/login" className={`${authLinkClass} gap-2`}>
      <ArrowLeft className="size-4 rtl-flip" aria-hidden="true" />
      {t("auth.backToLogin")}
    </Link>
  )
}

function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const { errors: fieldErrors, setErrors: setFieldErrors, clear: clearFieldError } = useFieldErrors()

  const forgotMutation = useForgotPasswordApiV1AuthForgotPasswordPost({
    mutation: {
      onSuccess: () => setSuccess(true),
      onError: (err) => setError(getApiErrorMessage(err, t("common.error"))),
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setError("")
    const errors = compactErrors({ email: emailError(email) })
    setFieldErrors(errors)
    if (errors.email) {
      focusFirstError(errors, ["email"])
      return
    }
    forgotMutation.mutate({ data: { email } })
  }

  return (
    <AuthPage title={t("auth.forgotPassword")} description={success ? undefined : t("auth.forgotPasswordDescription")} footer={<BackToLogin />}>
      {success ? (
        // the same words whether or not the address has an account (no account probing)
        <Alert tone="info">{t("auth.resetEmailSent")}</Alert>
      ) : (
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
          <Button type="submit" block loading={forgotMutation.isPending} className="mt-1">
            {t("auth.sendResetLink")}
          </Button>
        </form>
      )}
    </AuthPage>
  )
}
