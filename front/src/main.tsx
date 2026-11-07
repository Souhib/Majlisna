// Self-hosted faces (no font CDN under the enforced CSP). Before index.css so the
// @font-face rules are registered before the first styled paint.
import "./fonts"

import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { readRelease, startErrorReporting } from "./lib/report-error"
import { parseSearch } from "./lib/search-params"
import { routeTree } from "./routeTree.gen"
import "./index.css"
import "./i18n"

// The error tracker's SDK is fetched once the page is idle, and only in a build with a DSN;
// what fails before that is queued (lib/report-error.ts). The release is the commit the
// image stamped into index.html.
startErrorReporting({ dsn: import.meta.env.VITE_SENTRY_DSN, release: readRelease() })

const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
  // a hand-written share link's room code as written, even one that reads as a number (3E182)
  parseSearch,
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

const rootElement = document.getElementById("root")
if (rootElement && !rootElement.innerHTML) {
  const root = createRoot(rootElement)
  root.render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  )
}
