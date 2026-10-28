import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"

interface GameErrorFallbackProps {
  error?: Error
  onReset?: () => void
}

/**
 * What a game screen shows when it crashed: says so plainly, names the way out (try
 * again, or back to the rooms), and shows the error's own message when there is one.
 * A flat panel with an ember-edged alert: no icon in a tinted square, no float.
 *
 * A failed request shows the server's message in the reader's language
 * (`getApiErrorMessage`), never ky's "Request failed with status code 404: GET http://…",
 * whose unbroken URL also pushed a 390 px page sideways.
 */
export function GameErrorFallback({ error, onReset }: GameErrorFallbackProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const message = error ? getApiErrorMessage(error, error.message) : null

  return (
    <div className="page-wrap pt-10 pb-14">
      <Panel className="mx-auto max-w-[560px]">
        <h2 className="type-title">{t("common.error")}</h2>
        <p className="mt-2 text-[15px] leading-normal">{t("game.quiz.errorBody")}</p>
        {message ? (
          <Alert className="mt-4 wrap-anywhere" data-testid="game-error-message">
            {message}
          </Alert>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-2.5">
          {onReset ? <Button onClick={onReset}>{t("common.retry")}</Button> : null}
          <Button variant={onReset ? "secondary" : "primary"} onClick={() => navigate({ to: "/rooms" })}>
            {t("game.backToRoom")}
          </Button>
        </div>
      </Panel>
    </div>
  )
}
