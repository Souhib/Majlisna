import { GoogleOAuthProvider } from "@react-oauth/google"
import { createRootRoute, Outlet, useLocation } from "@tanstack/react-router"
import { MotionConfig } from "motion/react"
import React, { type ReactNode, Suspense, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Footer } from "@/components/layout/footer"
import { MainNav } from "@/components/layout/main-nav"
import { NotFound } from "@/components/NotFound"
import { setFallbackTitle } from "@/lib/document-title"
import { titleForPath } from "@/lib/route-title"
import { Toaster } from "@/components/ui/toaster"
import { t as motionT } from "@/lib/motion"
import { AuthProvider, QueryProvider, ThemeProvider } from "@/providers"

import { LanguageWelcomeModal } from "@/components/language/LanguageWelcomeModal"

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ""

function GoogleOAuthWrapper({ children }: { children: ReactNode }) {
  if (!GOOGLE_CLIENT_ID) return <>{children}</>
  return <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{children}</GoogleOAuthProvider>
}

const TanStackRouterDevtools =
  import.meta.env.PROD
    ? () => null
    : React.lazy(() =>
        import("@tanstack/react-router-devtools").then((mod) => ({
          default: mod.TanStackRouterDevtools,
        })),
      )

export const Route = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFound,
})

function RootLayout() {
  const { t, i18n } = useTranslation()
  const { pathname } = useLocation()
  // Game screens are the whole table: no footer under them.
  const showFooter = !pathname.startsWith("/game/")

  // The document title names the page, in its language (pages with a name from their
  // data refine it with useDocumentTitle).
  useEffect(() => {
    setFallbackTitle(titleForPath(pathname, t))
  }, [pathname, t, i18n.language])

  // Set document direction based on language (Arabic is RTL)
  useEffect(() => {
    const isRTL = i18n.language === "ar"
    document.documentElement.dir = isRTL ? "rtl" : "ltr"
    document.documentElement.lang = i18n.language
  }, [i18n.language])

  return (
    <GoogleOAuthWrapper>
    {/* reducedMotion="user": under prefers-reduced-motion, motion drops transforms and
        layout animation and keeps opacity and colour (the grammar's reduced form). */}
    <MotionConfig reducedMotion="user" transition={motionT.state}>
    <ThemeProvider defaultTheme="system">
      <QueryProvider>
        <AuthProvider>
            <div className="min-h-screen bg-background text-foreground flex flex-col">
              <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:start-3 focus:z-[60] focus:rounded-sm focus:bg-primary focus:px-4 focus:py-3 focus:text-[15px] focus:font-medium focus:text-primary-foreground"
              >
                {t("ui.skipToContent")}
              </a>
              <MainNav />
              {/* At least one screen tall under the nav, so the footer starts below the fold:
                  sitting at the bottom of a short loading page and then pushed down when
                  the content arrived, it made layout shifts in the "poor" band (CLS 0.7
                  on /achievements). */}
              <main id="main-content" className="min-h-[calc(100svh-var(--navh))] flex-1" tabIndex={-1}>
                {/* No route-level animation: sibling pages swap instantly (motion grammar,
                    MOTION_DELIGHT §9). The old AnimatePresence mode="wait" held a blank
                    screen for the exit on every navigation, game start included. */}
                <ErrorBoundary>
                  <Outlet />
                </ErrorBoundary>
              </main>
              {showFooter ? <Footer /> : null}
              <Toaster />
              <LanguageWelcomeModal />
            </div>
            <Suspense>
              <TanStackRouterDevtools position="bottom-right" />
            </Suspense>
        </AuthProvider>
      </QueryProvider>
    </ThemeProvider>
    </MotionConfig>
    </GoogleOAuthWrapper>
  )
}
