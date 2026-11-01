import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * A read that failed, said as such: the server's reason (or "This did not load") and a way
 * to ask again. Never the page's empty state: during an incident, "No games played" and
 * "No achievements yet" told a player with hundreds of games that their history was gone
 * (FR-7). The notebook and the word of the day say a failed read the same way.
 */
export function LoadFailed({
  error,
  onRetry,
  retrying = false,
  className,
  testId,
}: {
  error: unknown
  onRetry: () => void
  retrying?: boolean
  className?: string
  testId?: string
}) {
  const { t } = useTranslation()
  return (
    <div data-testid={testId} className={cn("grid justify-items-start gap-4", className)}>
      <Alert tone="error">{getApiErrorMessage(error, t("common.loadFailed"))}</Alert>
      <Button variant="secondary" onClick={onRetry} loading={retrying}>
        {t("common.retry")}
      </Button>
    </div>
  )
}
