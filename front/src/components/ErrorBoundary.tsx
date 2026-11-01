import { useRouterState } from "@tanstack/react-router"
import { Component, type ErrorInfo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { reportError } from "@/lib/report-error"

/** Set once 'Try again' has reloaded the tab for a chunk that failed to load (its value: the message). */
const CHUNK_RELOAD_KEY = "majlisna-chunk-reload"

/** A lazy chunk that did not load (Chrome, Firefox, Safari, and Vite's CSS preload). */
const CHUNK_LOAD_ERROR = /dynamically imported module|Importing a module script failed|Unable to preload CSS|ChunkLoadError/i

function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false
  return CHUNK_LOAD_ERROR.test(error.message) || CHUNK_LOAD_ERROR.test(error.name)
}

/**
 * A chunk that failed to load is never imported again in place (React's lazy and the router
 * keep the rejected promise), so the only repair is a fresh page: the new index.html names
 * the chunks of the current deploy. Once per error and tab (sessionStorage), so a chunk that
 * is really gone cannot reload the tab in a loop; without storage, no reload at all.
 */
function reloadOnceFor(error: Error): boolean {
  try {
    if (sessionStorage.getItem(CHUNK_RELOAD_KEY) === error.message) return false
    sessionStorage.setItem(CHUNK_RELOAD_KEY, error.message)
  } catch {
    return false
  }
  window.location.reload()
  return true
}

/**
 * What a crashed page shows: said plainly, with the repair (try again, then reload). The
 * technical message is folded away under "Technical details", for a screenshot sent to the
 * maker.
 */
function ErrorFallback({ message, onRetry }: { message?: string; onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="page-wrap grid min-h-[50vh] place-items-center py-16" role="alert">
      <div className="flex flex-col items-center">
        <EmptyState
          titleAs="h2"
          title={<span className="type-title text-[28px]">{t("ui.errorTitle")}</span>}
          description={t("ui.errorBody")}
          action={
            <>
              <Button onClick={onRetry}>{t("ui.tryAgain")}</Button>
              <Button variant="secondary" onClick={() => window.location.reload()}>
                {t("ui.reload")}
              </Button>
            </>
          }
        />
        {message ? (
          <details className="max-w-[46ch] px-4 text-center text-[13px] text-muted-foreground">
            <summary className="cursor-pointer">{t("ui.errorDetails")}</summary>
            <p className="mt-2 break-words" dir="auto">
              {message}
            </p>
          </details>
        ) : null}
      </div>
    </div>
  )
}

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface BoundaryProps extends Props {
  /** The page the boundary is on: a new one clears a caught error. */
  resetKey: string
}

interface State {
  error: Error | null
}

class Boundary extends Component<BoundaryProps, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    reportError(error, { source: "ErrorBoundary caught", extra: { componentStack: errorInfo.componentStack ?? "" } })
  }

  componentDidUpdate(prevProps: BoundaryProps, prevState: State) {
    // Only an error already on screen: the navigation that rendered the crash must not clear it.
    if (this.state.error && prevState.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  retry = () => {
    const { error } = this.state
    if (error && isChunkLoadError(error) && reloadOnceFor(error)) return
    this.setState({ error: null })
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback
      return <ErrorFallback message={this.state.error.message} onRetry={this.retry} />
    }
    return this.props.children
  }
}

/**
 * Catches a render error below it and shows the fallback, until the player moves to another
 * page (FR-10): the root one wraps <Outlet/> in __root.tsx, and a crash on one page used to
 * leave every page on "Something went wrong" until a manual reload.
 *
 * The page is the router's *resolved* location: the address changes before the new page's
 * matches are rendered, so a reset on it would draw the crashed page once more, catch it
 * again, and stay there. Not a `key` either: that would remount the whole tree under the
 * boundary on every navigation.
 */
export function ErrorBoundary({ children, fallback }: Props) {
  const pathname = useRouterState({ select: (s) => (s.resolvedLocation ?? s.location).pathname })
  return (
    <Boundary resetKey={pathname} fallback={fallback}>
      {children}
    </Boundary>
  )
}
