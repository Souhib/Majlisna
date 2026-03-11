import { createFileRoute, Link } from "@tanstack/react-router"
import { motion } from "motion/react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useForgotPasswordApiV1AuthForgotPasswordPost } from "@/api/generated"

export const Route = createFileRoute("/auth/forgot-password")({
  component: ForgotPasswordPage,
})

function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)

  const forgotMutation = useForgotPasswordApiV1AuthForgotPasswordPost({
    mutation: {
      onSuccess: () => setSuccess(true),
      onError: (err) => setError(getApiErrorMessage(err, t("common.error"))),
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    forgotMutation.mutate({ data: { email } })
  }

  const isLoading = forgotMutation.isPending

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="glass w-full max-w-md rounded-2xl p-8 space-y-8"
      >
        <div className="text-center">
          <h1 className="gradient-text text-3xl font-extrabold tracking-tight">{t("auth.forgotPassword")}</h1>
          <p className="mt-2 text-muted-foreground">{t("auth.forgotPasswordDescription")}</p>
        </div>

          {success ? (
            <div className="rounded-2xl bg-primary/10 p-4 text-center">
              <p className="text-sm text-primary font-medium">{t("auth.resetEmailSent")}</p>
              <Link to="/auth/login" className="mt-4 inline-block text-sm font-medium text-primary hover:text-primary transition-all duration-200 hover:underline">
                {t("auth.backToLogin")}
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="rounded-2xl bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
              )}
              <div>
                <label htmlFor="email" className="block text-sm font-medium mb-1">
                  {t("auth.email")}
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full rounded-xl border-border/50 bg-background/80 px-3 py-2 text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/30"
                  placeholder="you@example.com"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full rounded-2xl bg-gradient-to-r from-primary to-primary/90 px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:bg-glow disabled:opacity-50 transition-all duration-200"
              >
                {isLoading ? t("common.loading") : t("auth.sendResetLink")}
              </button>
              <p className="text-center text-sm text-muted-foreground">
                <Link to="/auth/login" className="font-medium text-primary hover:text-primary transition-all duration-200 hover:underline">
                  {t("auth.backToLogin")}
                </Link>
              </p>
            </form>
          )}
      </motion.div>
    </div>
  )
}
