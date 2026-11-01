import { GoogleOAuthProvider, useGoogleLogin } from "@react-oauth/google"
import { useNavigate } from "@tanstack/react-router"
import { type ReactNode, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import client, { getApiErrorMessage } from "@/api/client"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/providers/AuthProvider"

/** Read at render, not at import: a build without the variable must still render its pages. */
export function googleClientId(): string {
  return import.meta.env.VITE_GOOGLE_CLIENT_ID || ""
}

/**
 * Google's provider, mounted only where a Google control is on screen. It injects Google's
 * script (accounts.google.com/gsi/client, about 100 kB) on mount and removes it on unmount,
 * so the script loads on the pages that show the button and nowhere else (the root layout
 * used to wrap the whole app in it). Renders nothing in a build without a client id: the
 * hooks under it would throw "must be used within GoogleOAuthProvider", which used to take
 * the whole login and register pages down. Anything else that calls a Google hook (account
 * deletion's "Confirm with Google") wraps itself the same way.
 */
export function WithGoogleOAuth({ children, onScriptLoadError }: { children: ReactNode; onScriptLoadError?: () => void }) {
  const clientId = googleClientId()
  if (!clientId) return null
  return (
    <GoogleOAuthProvider clientId={clientId} onScriptLoadError={onScriptLoadError}>
      {children}
    </GoogleOAuthProvider>
  )
}

interface SocialLoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  is_new_user: boolean
  user: { id: string; username: string; email: string }
}

/** Google's own "G" in its four colours, unaltered (its branding rules), for our Google buttons. */
export function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  )
}

/** "Continue with Google" on the sign-in and sign-up pages; nothing without a client id. */
export function GoogleLoginButton({ redirectTo }: { redirectTo?: string }) {
  return (
    <WithGoogleOAuth>
      <GoogleLoginButtonInner redirectTo={redirectTo} />
    </WithGoogleOAuth>
  )
}

function GoogleLoginButtonInner({ redirectTo }: { redirectTo?: string }) {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setIsLoading(true)
      try {
        const response = await client<SocialLoginResponse>({
          method: "POST",
          url: "/api/v1/auth/social/login",
          data: {
            provider: "google",
            access_token: tokenResponse.access_token,
          },
        })

        const data = response.data

        login(data.access_token, data.expires_in, {
          id: data.user.id,
          username: data.user.username,
          email: data.user.email,
        })

        if (data.is_new_user) {
          toast.success(t("auth.socialWelcomeNew"))
        } else {
          toast.success(t("auth.socialWelcomeBack"))
        }

        navigate({ href: redirectTo ?? "/" })
      } catch (err: unknown) {
        toast.error(getApiErrorMessage(err, t("auth.socialLoginFailed")))
      } finally {
        setIsLoading(false)
      }
    },
    onError: () => {
      toast.error(t("auth.socialLoginFailed"))
    },
  })

  return (
    <div className="grid gap-5">
      {/* "or" between two hairlines: no capitals, no letter-spacing (Arabic has neither) */}
      <p className="flex items-center gap-4 text-[13px] leading-none text-muted-foreground">
        <span aria-hidden="true" className="h-px flex-1 bg-line" />
        {t("auth.orContinueWith")}
        <span aria-hidden="true" className="h-px flex-1 bg-line" />
      </p>

      {/* Our frame (a secondary button), Google's own "G" in its own four colours,
          unaltered, as its branding rules ask. */}
      <Button
        variant="secondary"
        block
        loading={isLoading}
        iconStart={<GoogleIcon />}
        onClick={() => {
          if (!isLoading) googleLogin()
        }}
        data-testid="google-login-button"
      >
        {t("auth.continueWithGoogle")}
      </Button>
    </div>
  )
}
