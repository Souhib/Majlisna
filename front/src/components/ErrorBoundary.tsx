import * as Sentry from "@sentry/react"
import { Component, type ErrorInfo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"

/**
 * What a crashed page shows: said plainly, with the repair (try again, then reload).
 * The technical message stays visible but quiet, for a screenshot sent to the maker.
 */
function ErrorFallback({ message, onRetry }: { message?: string; onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="page-wrap grid min-h-[50vh] place-items-center py-16" role="alert">
      <EmptyState
        titleAs="h2"
        title={<span className="type-title text-[28px]">{t("ui.errorTitle")}</span>}
        description={
          <>
            {t("ui.errorBody")}
            {message ? (
              <span className="mt-3 block text-[13px] text-muted-foreground" dir="auto">
                {message}
              </span>
            ) : null}
          </>
        }
        action={
          <>
            <Button onClick={onRetry}>{t("ui.tryAgain")}</Button>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              {t("ui.reload")}
            </Button>
          </>
        }
      />
    </div>
  )
}

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo)
    Sentry.captureException(error, { extra: { componentStack: errorInfo.componentStack } })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return <ErrorFallback message={this.state.error?.message} onRetry={() => this.setState({ hasError: false, error: undefined })} />
    }
    return this.props.children
  }
}
