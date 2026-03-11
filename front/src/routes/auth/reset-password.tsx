import { createFileRoute, Link, useSearch } from "@tanstack/react-router"
import { motion } from "motion/react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useResetPasswordApiV1AuthResetPasswordPost } from "@/api/generated"

export const Route = createFileRoute("/auth/reset-password")({
  component: ResetPasswordPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || "",
  }),
})

function ResetPasswordPage() {
  const { t } = useTranslation()
  const { token } = useSearch({ from: "/auth/reset-password" })
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)

  const resetMutation = useResetPasswordApiV1AuthResetPasswordPost({
    mutation: {
      onSuccess: () => setSuccess(true),
      onError: (err) => setError(getApiErrorMessage(err, t("common.error"))),
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (password !== confirmPassword) {
      setError(t("auth.passwordsDoNotMatch"))
      return
    }

    if (password.length < 5) {
      setError(t("auth.passwordTooShort"))
      return
    }

    resetMutation.mutate({ data: { token, new_password: password } })
  }

  const isLoading = resetMutation.isPending

  if (!token) {
    return (
      <div className="flex min-h-[80vh] items-center justify-center px-4">
        <div className="glass animate-scale-in w-full max-w-md rounded-2xl p-8 text-center space-y-4">
          <p className="text-destructive">{t("auth.invalidOrExpiredToken")}</p>
          <Link to="/auth/login" className="text-sm font-medium text-primary hover:text-primary transition-all duration-200 hover:underline">
            {t("auth.backToLogin")}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="glass w-full max-w-md rounded-2xl p-8 space-y-8"
      >
        <div className="text-center">
          <h1 className="gradient-text text-3xl font-extrabold tracking-tight">{t("auth.resetPassword")}</h1>
          <p className="mt-2 text-muted-foreground">{t("auth.resetPasswordDescription")}</p>
        </div>

          {success ? (
            <div className="rounded-2xl bg-primary/10 p-4 text-center">
              <p className="text-sm text-primary font-medium">{t("auth.passwordResetSuccess")}</p>
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
                <label htmlFor="password" className="block text-sm font-medium mb-1">
                  {t("auth.newPassword")}
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={5}
                  className="w-full rounded-xl border-border/50 bg-background/80 px-3 py-2 text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/30"
                  placeholder="********"
                />
              </div>
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium mb-1">
                  {t("auth.confirmPassword")}
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={5}
                  className="w-full rounded-xl border-border/50 bg-background/80 px-3 py-2 text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/30"
                  placeholder="********"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full rounded-2xl bg-gradient-to-r from-primary to-primary/90 px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:bg-glow disabled:opacity-50 transition-all duration-200"
              >
                {isLoading ? t("common.loading") : t("auth.resetPassword")}
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
