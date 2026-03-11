import { createFileRoute, Link, useSearch } from "@tanstack/react-router"
import { motion } from "motion/react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { verifyEmailApiV1AuthVerifyEmailPost } from "@/api/generated"

export const Route = createFileRoute("/auth/verify-email")({
  component: VerifyEmailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || "",
  }),
})

function VerifyEmailPage() {
  const { t } = useTranslation()
  const { token } = useSearch({ from: "/auth/verify-email" })
  const [status, setStatus] = useState<"loading" | "success" | "error">(token ? "loading" : "error")
  const [error, setError] = useState("")

  useEffect(() => {
    if (!token) {
      setStatus("error")
      setError(t("auth.invalidOrExpiredToken"))
      return
    }

    const verify = async () => {
      try {
        await verifyEmailApiV1AuthVerifyEmailPost({ token })
        setStatus("success")
      } catch (err) {
        setStatus("error")
        setError(getApiErrorMessage(err, t("auth.invalidOrExpiredToken")))
      }
    }

    verify()
  }, [token, t])

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="glass w-full max-w-md rounded-2xl p-8 space-y-6 text-center"
      >
          {status === "loading" && (
            <>
              <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-muted-foreground">{t("auth.verifyingEmail")}</p>
            </>
          )}

          {status === "success" && (
            <>
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                <svg className="h-8 w-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h1 className="gradient-text text-2xl font-extrabold tracking-tight">{t("auth.emailVerified")}</h1>
              <p className="text-muted-foreground">{t("auth.emailVerifiedDescription")}</p>
              <Link
                to="/auth/login"
                className="inline-block rounded-2xl bg-gradient-to-r from-primary to-primary/90 px-6 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:bg-glow transition-all duration-200"
              >
                {t("auth.login")}
              </Link>
            </>
          )}

          {status === "error" && (
            <>
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
                <svg className="h-8 w-8 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h1 className="text-2xl font-extrabold tracking-tight text-destructive">{t("auth.verificationFailed")}</h1>
              <p className="text-muted-foreground">{error}</p>
              <Link
                to="/auth/login"
                className="inline-block text-sm font-medium text-primary hover:text-primary transition-all duration-200 hover:underline"
              >
                {t("auth.backToLogin")}
              </Link>
            </>
          )}
      </motion.div>
    </div>
  )
}
