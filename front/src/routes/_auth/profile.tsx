import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { Award, BarChart3, Check, Gamepad2, KeyRound, Pencil, Trash2, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useAuth } from "@/providers/AuthProvider"
import { getApiErrorMessage } from "@/api/client"
import {
  useUpdateUserApiV1UsersUserIdPatch,
  useDeleteAccountApiV1UsersMeAccountDelete,
  useUpdateUserPasswordApiV1UsersUserIdPasswordPatch,
} from "@/api/generated"

export const Route = createFileRoute("/_auth/profile")({
  component: ProfilePage,
})

function ProfilePage() {
  const { t } = useTranslation()
  const { user, setUser, logout } = useAuth()
  const navigate = useNavigate()

  const [isEditingUsername, setIsEditingUsername] = useState(false)
  const [newUsername, setNewUsername] = useState(user?.username ?? "")

  const [showPasswordForm, setShowPasswordForm] = useState(false)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deletePassword, setDeletePassword] = useState("")

  const updateUserMutation = useUpdateUserApiV1UsersUserIdPatch()
  const deleteAccountMutation = useDeleteAccountApiV1UsersMeAccountDelete()
  const changePasswordMutation = useUpdateUserPasswordApiV1UsersUserIdPasswordPatch()

  const isSavingUsername = updateUserMutation.isPending
  const isSavingPassword = changePasswordMutation.isPending
  const isDeletingAccount = deleteAccountMutation.isPending

  const handleSaveUsername = async () => {
    if (!user || !newUsername.trim() || newUsername === user.username) {
      setIsEditingUsername(false)
      return
    }
    try {
      const updated = await updateUserMutation.mutateAsync({
        user_id: user.id,
        data: { username: newUsername.trim() },
      }) as { id: string; username: string; email_address: string; is_active: boolean; is_admin: boolean }
      setUser({
        id: updated.id,
        username: updated.username,
        email: updated.email_address,
        is_active: updated.is_active,
        is_admin: updated.is_admin,
      })
      localStorage.setItem(
        "majlisna-user-data",
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
    }
  }

  const handleDeleteAccount = async () => {
    if (!deletePassword || isDeletingAccount) return
    try {
      await deleteAccountMutation.mutateAsync({ data: { password: deletePassword } })
      logout()
      navigate({ to: "/" })
      toast.success(t("profile.accountDeleted"))
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    }
  }

  const handleChangePassword = async () => {
    if (!user || currentPassword.length < 1 || newPassword.length < 5) return
    try {
      await changePasswordMutation.mutateAsync({
        user_id: user.id,
        data: { current_password: currentPassword, new_password: newPassword },
      })
      toast.success(t("profile.passwordChanged"))
      setShowPasswordForm(false)
      setCurrentPassword("")
      setNewPassword("")
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 animate-slide-up">
      {/* User Info */}
      <div className="glass rounded-2xl p-8 mb-8 animate-scale-in">
        <div className="flex items-center gap-5">
          <div className="relative">
            <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-primary to-accent opacity-75 blur-sm" />
            <div className="relative flex h-18 w-18 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/80 text-2xl font-extrabold text-primary-foreground shadow-lg shadow-primary/25">
              {user?.username?.charAt(0).toUpperCase()}
            </div>
          </div>
          <div className="flex-1">
            {isEditingUsername ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="rounded-xl border border-border/30 bg-background px-4 py-2 text-lg font-extrabold tracking-tight focus:outline-none focus:ring-2 focus:ring-primary transition-all duration-200"
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
                  className="rounded-xl p-2 text-primary hover:bg-primary/10 bg-glow transition-all duration-200"
                >
                  <Check className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsEditingUsername(false)
                    setNewUsername(user?.username ?? "")
                  }}
                  className="rounded-xl p-2 text-muted-foreground hover:bg-muted transition-all duration-200"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight gradient-text">{user?.username}</h1>
                <button
                  type="button"
                  onClick={() => setIsEditingUsername(true)}
                  className="rounded-xl p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all duration-200"
                  aria-label={t("profile.editUsername")}
                >
                  <Pencil className="h-4 w-4" />
                </button>
              </div>
            )}
            <p className="text-muted-foreground mt-1">{user?.email}</p>
          </div>
        </div>

        {/* Change Password */}
        <div className="mt-6 pt-6 border-t border-border/30">
          {showPasswordForm ? (
            <div className="space-y-3 animate-scale-in">
              <label className="text-sm font-medium">{t("profile.changePassword")}</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder={t("profile.currentPassword")}
                className="w-full rounded-xl border border-border/30 bg-background px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary transition-all duration-200"
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setShowPasswordForm(false)
                    setCurrentPassword("")
                    setNewPassword("")
                  }
                }}
              />
              <div className="flex items-center gap-2">
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("profile.newPassword")}
                  className="rounded-xl border border-border/30 bg-background px-4 py-2.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-primary transition-all duration-200"
                  minLength={5}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleChangePassword()
                    if (e.key === "Escape") {
                      setShowPasswordForm(false)
                      setCurrentPassword("")
                      setNewPassword("")
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={handleChangePassword}
                  disabled={isSavingPassword || currentPassword.length < 1 || newPassword.length < 5}
                  className="rounded-xl bg-gradient-to-r from-primary to-primary/90 px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg transition-all duration-200 disabled:opacity-50"
                >
                  {t("common.save")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordForm(false)
                    setCurrentPassword("")
                    setNewPassword("")
                  }}
                  className="rounded-xl px-5 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted transition-all duration-200"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowPasswordForm(true)}
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary transition-all duration-200"
            >
              <KeyRound className="h-4 w-4" />
              {t("profile.changePassword")}
            </button>
          )}
        </div>
      </div>

      {/* Danger Zone */}
      <div className="glass rounded-2xl border-destructive/30 p-8 mb-8">
        <h2 className="text-lg font-extrabold tracking-tight text-destructive flex items-center gap-2">
          <Trash2 className="h-5 w-5" />
          {t("profile.deleteAccount")}
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("profile.deleteAccountDescription")}</p>

        {showDeleteConfirm ? (
          <div className="mt-4 space-y-3 animate-scale-in">
            <p className="text-sm font-medium text-destructive">{t("profile.deleteAccountWarning")}</p>
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                placeholder={t("profile.enterPasswordToDelete")}
                className="rounded-xl border border-destructive/30 bg-background px-4 py-2.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-destructive transition-all duration-200"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleDeleteAccount()
                  if (e.key === "Escape") {
                    setShowDeleteConfirm(false)
                    setDeletePassword("")
                  }
                }}
              />
              <button
                type="button"
                onClick={handleDeleteAccount}
                disabled={isDeletingAccount || !deletePassword}
                className="rounded-xl bg-destructive px-5 py-2.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 shadow-md shadow-destructive/20 transition-all duration-200 disabled:opacity-50"
              >
                {isDeletingAccount ? t("common.loading") : t("profile.deleteAccountConfirm")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowDeleteConfirm(false)
                  setDeletePassword("")
                }}
                className="rounded-xl px-5 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted transition-all duration-200"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="mt-4 rounded-xl border border-destructive/30 px-5 py-2.5 text-sm font-medium text-destructive hover:bg-destructive/10 transition-all duration-200"
          >
            {t("profile.deleteAccount")}
          </button>
        )}
      </div>

      {/* Quick Links */}
      <div className="grid gap-4 md:grid-cols-3">
        <Link
          to="/stats"
          className="card-hover glass rounded-2xl p-6 hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 mb-3">
            <BarChart3 className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-extrabold tracking-tight">{t("stats.title")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.viewStats")}</p>
        </Link>

        <Link
          to="/achievements"
          className="card-hover glass rounded-2xl p-6 hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10 mb-3">
            <Award className="h-6 w-6 text-accent" />
          </div>
          <h3 className="font-extrabold tracking-tight">{t("achievements.title")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.viewAchievements")}</p>
        </Link>

        <Link
          to="/rooms"
          className="card-hover glass rounded-2xl p-6 hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 mb-3">
            <Gamepad2 className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-extrabold tracking-tight">{t("nav.rooms")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("profile.joinOrCreate")}</p>
        </Link>
      </div>
    </div>
  )
}
