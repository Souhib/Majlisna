import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { motion } from "motion/react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { useRegisterApiV1AuthRegisterPost } from "@/api/generated"
import { useAuth } from "@/providers/AuthProvider"

export const Route = createFileRoute("/auth/register")({
  component: RegisterPage,
})

function RegisterPage() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")

  const registerMutation = useRegisterApiV1AuthRegisterPost({
    mutation: {
      onSuccess: (data) => {
        const d = data as unknown as { access_token: string; refresh_token: string; token_type: string; user?: { id: string; username: string; email: string; is_active: boolean; is_admin: boolean } }
        login(d.access_token, d.refresh_token, 900, d.user || undefined)
        navigate({ to: "/" })
      },
      onError: (err) => {
        setError(getApiErrorMessage(err, t("errors.api.userAlreadyExists")))
      },
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    registerMutation.mutate({ data: { username, email_address: email, password } })
  }

  const isLoading = registerMutation.isPending

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="glass w-full max-w-md rounded-2xl p-8 space-y-8"
      >
        <div className="text-center">
          <h1 className="gradient-text text-3xl font-extrabold tracking-tight">{t("auth.registerTitle")}</h1>
          <p className="mt-2 text-muted-foreground">{t("auth.registerDescription")}</p>
        </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="rounded-2xl bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
            )}

            <div>
              <label htmlFor="username" className="block text-sm font-medium mb-1">
                {t("auth.username")}
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full rounded-xl border-border/50 bg-background/80 px-3 py-2 text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/30"
                placeholder="Your username"
              />
            </div>

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

            <div>
              <label htmlFor="password" className="block text-sm font-medium mb-1">
                {t("auth.password")}
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="w-full rounded-xl border-border/50 bg-background/80 px-3 py-2 text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/30"
                placeholder="********"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-2xl bg-gradient-to-r from-primary to-primary/90 px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:bg-glow disabled:opacity-50 transition-all duration-200"
            >
              {isLoading ? t("common.loading") : t("auth.register")}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            {t("auth.hasAccount")}{" "}
            <Link to="/auth/login" className="font-medium text-primary hover:text-primary transition-all duration-200 hover:underline">
              {t("auth.login")}
            </Link>
          </p>
      </motion.div>
    </div>
  )
}
