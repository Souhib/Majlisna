import { createRootRoute, Outlet, useLocation } from "@tanstack/react-router"
import { AnimatePresence, motion } from "motion/react"
import React, { Suspense, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Footer } from "@/components/layout/footer"
import { MainNav } from "@/components/layout/main-nav"
import { NotFound } from "@/components/NotFound"
import { Toaster } from "sonner"
import { AuthProvider, QueryProvider, ThemeProvider } from "@/providers"
import { GoogleMapsProvider } from "@/providers/GoogleMapsProvider"

const TanStackRouterDevtools =
  process.env.NODE_ENV === "production"
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
  const location = useLocation()
  const { i18n } = useTranslation()

  // Set document direction based on language (Arabic is RTL)
  useEffect(() => {
    const isRTL = i18n.language === "ar"
    document.documentElement.dir = isRTL ? "rtl" : "ltr"
    document.documentElement.lang = i18n.language
  }, [i18n.language])

  return (
    <ThemeProvider defaultTheme="system">
      <QueryProvider>
        <AuthProvider>
          <GoogleMapsProvider>
            <div className="min-h-screen bg-background text-foreground flex flex-col">
              <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md focus:shadow-lg"
              >
                Skip to main content
              </a>
              <MainNav />
              <main id="main-content" className="flex-1" tabIndex={-1}>
                <ErrorBoundary>
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={location.pathname}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -20 }}
                      transition={{ duration: 0.3 }}
                    >
                      <Outlet />
                    </motion.div>
                  </AnimatePresence>
                </ErrorBoundary>
              </main>
              <Footer />
              <Toaster position="bottom-right" richColors closeButton />
            </div>
            <Suspense>
              <TanStackRouterDevtools position="bottom-right" />
            </Suspense>
          </GoogleMapsProvider>
        </AuthProvider>
      </QueryProvider>
    </ThemeProvider>
  )
}
