import { createFileRoute, Link, useSearch } from "@tanstack/react-router"
import { ArrowLeft, ArrowRight } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage, gotNoApiAnswer } from "@/api/client"
import { verifyEmailApiV1AuthVerifyEmailPost } from "@/api/generated"
import { AuthPage, authLinkClass } from "@/components/auth/AuthPage"
import { apiErrorKey, TOKEN_REJECTED_KEY } from "@/components/auth/validation"
import { Alert } from "@/components/ui/alert"
import { BusyLozenges, Button } from "@/components/ui/button"
import { scrubTokenFromUrl } from "@/lib/auth"

export const Route = createFileRoute("/auth/verify-email")({
  component: VerifyEmailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || "",
  }),
})

/** "unanswered": the request got no answer (offline, a deploy), so the token may still be good. */
type Status = "loading" | "success" | "error" | "unanswered"

function VerifyEmailPage() {
  const { t } = useTranslation()
  const { token: tokenFromLink } = useSearch({ from: "/auth/verify-email" })
  // The link's token, read once and kept in memory: the address drops it right away, so
  // the history, an analytics page view or a screenshot never holds it (SEC F06). Links
  // already sent keep working. A reload can no longer resend it, hence "Retry" below.
  const [token] = useState(tokenFromLink)
  const [status, setStatus] = useState<Status>(token ? "loading" : "error")
  /** The server's own words when it gave any; otherwise the page says it in the current language. */
  const [serverMessage, setServerMessage] = useState("")
  /** Sends asked for: the first on load, one more per "Retry". */
  const [attempt, setAttempt] = useState(0)
  /** The send already made: a verification link is used once. */
  const sentFor = useRef<number | null>(null)

  useEffect(() => {
    scrubTokenFromUrl()
  }, [])

  // The effect used to depend on `t` as well, so switching language on this page (and
  // StrictMode's double mount in development) posted the token a second time; the
  // second call found it spent and turned a verified email into "Verification failed".
  useEffect(() => {
    if (!token || sentFor.current === attempt) return
    sentFor.current = attempt
    verifyEmailApiV1AuthVerifyEmailPost({ token })
      .then(() => setStatus("success"))
      .catch((err: unknown) => {
        if (gotNoApiAnswer(err)) {
          setStatus("unanswered")
          return
        }
        // a refused link is said in the page's language (the server's key has no translation)
        setServerMessage(apiErrorKey(err) === TOKEN_REJECTED_KEY ? "" : getApiErrorMessage(err, ""))
        setStatus("error")
      })
  }, [token, attempt])

  const retry = () => {
    setStatus("loading")
    setAttempt((n) => n + 1)
  }

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
      <AuthPage title={t("auth.emailVerified")} description={t("auth.emailVerifiedDescription")}>
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
      {status === "unanswered" ? (
        <div className="grid gap-5">
          <Alert>
            <p>{t("errors.network")}</p>
          </Alert>
          <Button block onClick={retry}>
            {t("common.retry")}
          </Button>
        </div>
      ) : (
        <Alert>
          <p>{serverMessage || t("auth.invalidOrExpiredToken")}</p>
          <p className="mt-1 text-muted-foreground">{t("auth.verificationFailedHelp")}</p>
        </Alert>
      )}
    </AuthPage>
  )
}
