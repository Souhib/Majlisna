import { createFileRoute, Link } from "@tanstack/react-router"
import { Award, BarChart3, Check, Gamepad2, KeyRound, Pencil, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useAuth } from "@/providers/AuthProvider"
import apiClient, { getApiErrorMessage } from "@/api/client"

export const Route = createFileRoute("/_auth/profile")({
  component: ProfilePage,
})

function ProfilePage() {
  const { t } = useTranslation()
  const { user, setUser } = useAuth()

  const [isEditingUsername, setIsEditingUsername] = useState(false)
  const [newUsername, setNewUsername] = useState(user?.username ?? "")
  const [isSavingUsername, setIsSavingUsername] = useState(false)

  const [showPasswordForm, setShowPasswordForm] = useState(false)
  const [newPassword, setNewPassword] = useState("")
  const [isSavingPassword, setIsSavingPassword] = useState(false)

  const handleSaveUsername = async () => {
    if (!user || !newUsername.trim() || newUsername === user.username) {
      setIsEditingUsername(false)
      return
    }
    setIsSavingUsername(true)
    try {
      const res = await apiClient({
        method: "PATCH",
        url: `/api/v1/users/${user.id}`,
        data: { username: newUsername.trim(), email_address: user.email },
      })
      const updated = res.data as { id: string; username: string; email_address: string; is_active: boolean; is_admin: boolean }
      setUser({
        id: updated.id,
        username: updated.username,
        email: updated.email_address,
        is_active: updated.is_active,
        is_admin: updated.is_admin,
      })
      localStorage.setItem(
        "ipg-user-data",
        JSON.stringify({
          id: updated.id,
          username: updated.username,
          email: updated.email_address,
          is_active: updated.is_active,
          is_admin: updated.is_admin,
        }),
      )
      toast.success(t("profile.saved"))
      setIsEditingUsername(false)
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setIsSavingUsername(false)
    }
  }

  const handleChangePassword = async () => {
    if (!user || newPassword.length < 5) return
    setIsSavingPassword(true)
    try {
      await apiClient({
        method: "PATCH",
        url: `/api/v1/users/${user.id}/password`,
        data: { password: newPassword },
      })
      toast.success(t("profile.passwordChanged"))
      setShowPasswordForm(false)
      setNewPassword("")
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setIsSavingPassword(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* User Info */}
      <div className="rounded-xl border bg-card p-8 mb-8">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold text-primary">
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <div className="flex-1">
            {isEditingUsername ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="rounded-md border bg-background px-3 py-1.5 text-lg font-bold focus:outline-none focus:ring-2 focus:ring-primary"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveUsername()
                    if (e.key === "Escape") {
                      setIsEditingUsername(false)
                      setNewUsername(user?.username ?? "")
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={handleSaveUsername}
                  disabled={isSavingUsername}
                  className="rounded-md p-1.5 text-primary hover:bg-primary/10 transition-colors"
                >
                  <Check className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsEditingUsername(false)
                    setNewUsername(user?.username ?? "")
                  }}
                  className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold">{user?.username}</h1>
                <button
                  type="button"
                  onClick={() => setIsEditingUsername(true)}
                  className="rounded-md p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                  aria-label={t("profile.editUsername")}
                >
                  <Pencil className="h-4 w-4" />
                </button>
              </div>
            )}
            <p className="text-muted-foreground">{user?.email}</p>
          </div>
        </div>

        {/* Change Password */}
        <div className="mt-6 pt-6 border-t">
          {showPasswordForm ? (
            <div className="space-y-3">
              <label className="text-sm font-medium">{t("profile.newPassword")}</label>
              <div className="flex items-center gap-2">
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("profile.newPassword")}
                  className="rounded-md border bg-background px-3 py-2 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-primary"
                  minLength={5}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleChangePassword()
                    if (e.key === "Escape") {
                      setShowPasswordForm(false)
                      setNewPassword("")
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={handleChangePassword}
                  disabled={isSavingPassword || newPassword.length < 5}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {t("common.save")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordForm(false)
                    setNewPassword("")
                  }}
                  className="rounded-md px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowPasswordForm(true)}
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary transition-colors"
            >
              <KeyRound className="h-4 w-4" />
              {t("profile.changePassword")}
            </button>
          )}
        </div>
      </div>

      {/* Quick Links */}
      <div className="grid gap-4 md:grid-cols-3">
        <Link
          to="/stats"
          className="rounded-xl border bg-card p-6 hover:shadow-md transition-shadow"
        >
          <BarChart3 className="h-8 w-8 text-primary mb-3" />
          <h3 className="font-semibold">{t("stats.title")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.viewStats")}</p>
        </Link>

        <Link
          to="/achievements"
          className="rounded-xl border bg-card p-6 hover:shadow-md transition-shadow"
        >
          <Award className="h-8 w-8 text-accent mb-3" />
          <h3 className="font-semibold">{t("achievements.title")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.viewAchievements")}</p>
        </Link>

        <Link
          to="/rooms"
          className="rounded-xl border bg-card p-6 hover:shadow-md transition-shadow"
        >
          <Gamepad2 className="h-8 w-8 text-primary mb-3" />
          <h3 className="font-semibold">{t("nav.rooms")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.joinOrCreate")}</p>
        </Link>
      </div>
    </div>
  )
}
