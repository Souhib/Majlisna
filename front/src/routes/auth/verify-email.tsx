import { createFileRoute, Link, useSearch } from "@tanstack/react-router"
import { ArrowLeft, ArrowRight } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { verifyEmailApiV1AuthVerifyEmailPost } from "@/api/generated"
import { AuthPage, authLinkClass } from "@/components/auth/AuthPage"
import { apiErrorKey, TOKEN_REJECTED_KEY } from "@/components/auth/validation"
import { Alert } from "@/components/ui/alert"
import { BusyLozenges, Button } from "@/components/ui/button"

export const Route = createFileRoute("/auth/verify-email")({
  component: VerifyEmailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || "",
  }),
})

type Status = "loading" | "success" | "error"

function VerifyEmailPage() {
  const { t } = useTranslation()
  const { token } = useSearch({ from: "/auth/verify-email" })
  const [status, setStatus] = useState<Status>(token ? "loading" : "error")
  /** The server's own words when it gave any; otherwise the page says it in the current language. */
  const [serverMessage, setServerMessage] = useState("")
  /** The token already sent: a verification link is used once. */
  const sentFor = useRef<string | null>(null)

  // The effect used to depend on `t` as well, so switching language on this page (and
  // StrictMode's double mount in development) posted the token a second time; the
  // second call found it spent and turned a verified email into "Verification failed".
  useEffect(() => {
    if (!token || sentFor.current === token) return
    sentFor.current = token
    verifyEmailApiV1AuthVerifyEmailPost({ token })
      .then(() => setStatus("success"))
      .catch((err: unknown) => {
        // a refused link is said in the page's language (the server's key has no translation)
        setServerMessage(apiErrorKey(err) === TOKEN_REJECTED_KEY ? "" : getApiErrorMessage(err, ""))
        setStatus("error")
      })
  }, [token])

  if (status === "loading") {
    return (
      <AuthPage title={t("auth.verifyingEmail")}>
        <p role="status" className="flex items-center gap-3 text-[15px] text-muted-foreground">
          <BusyLozenges className="text-brass" />
          <span className="sr-only">{t("auth.verifyingEmail")}</span>
        </p>
      </AuthPage>
    )
  }

  if (status === "success") {
    return (
      <AuthPage
        title={t("auth.emailVerified")}
        description={t("auth.emailVerifiedDescription")}
      >
        <Button asChild block iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
          <Link to="/auth/login">{t("auth.login")}</Link>
        </Button>
      </AuthPage>
    )
  }

  return (
    <AuthPage
      title={t("auth.verificationFailed")}
      footer={
        <Link to="/auth/login" className={`${authLinkClass} gap-2`}>
          <ArrowLeft className="size-4 rtl-flip" aria-hidden="true" />
          {t("auth.backToLogin")}
        </Link>
      }
    >
      <Alert>
        <p>{serverMessage || t("auth.invalidOrExpiredToken")}</p>
        <p className="mt-1 text-muted-foreground">{t("auth.verificationFailedHelp")}</p>
      </Alert>
    </AuthPage>
  )
}
