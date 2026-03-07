import { Settings } from "lucide-react"
import { memo, useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import apiClient, { getApiErrorMessage } from "@/api/client"

interface RoomSettingsProps {
  roomId: string
  settings: Record<string, unknown> | null
  gameType: "undercover" | "codenames"
  playerCount: number
}

const TIMER_OPTIONS = [0, 15, 30, 45, 60, 90, 120, 180]

export const RoomSettings = memo(function RoomSettings({
  roomId,
  settings,
  gameType,
  playerCount,
}: RoomSettingsProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const [descriptionTimer, setDescriptionTimer] = useState(0)
  const [votingTimer, setVotingTimer] = useState(0)
  const [codenamesClueTimer, setCodenamesClueTimer] = useState(0)
  const [codenamesGuessTimer, setCodenamesGuessTimer] = useState(0)
  const [enableMrWhite, setEnableMrWhite] = useState(true)

  useEffect(() => {
    if (settings) {
      if (settings.description_timer !== undefined) setDescriptionTimer(settings.description_timer as number)
      if (settings.voting_timer !== undefined) setVotingTimer(settings.voting_timer as number)
      if (settings.codenames_clue_timer !== undefined) setCodenamesClueTimer(settings.codenames_clue_timer as number)
      if (settings.codenames_guess_timer !== undefined) setCodenamesGuessTimer(settings.codenames_guess_timer as number)
      if (settings.enable_mr_white !== undefined) setEnableMrWhite(settings.enable_mr_white as boolean)
    }
  }, [settings])

  const timerLabel = (val: number) => (val === 0 ? t("room.noLimit") : `${val}s`)

  const handleSave = useCallback(async () => {
    setIsSaving(true)
    try {
      const payload: Record<string, unknown> = {}
      if (gameType === "undercover") {
        payload.description_timer = descriptionTimer
        payload.voting_timer = votingTimer
        payload.enable_mr_white = enableMrWhite
      } else {
        payload.codenames_clue_timer = codenamesClueTimer
        payload.codenames_guess_timer = codenamesGuessTimer
      }
      await apiClient({
        method: "PATCH",
        url: `/api/v1/rooms/${roomId}/settings`,
        data: payload,
      })
      toast.success(t("room.settingsSaved"))
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to save settings"))
    } finally {
      setIsSaving(false)
    }
  }, [roomId, gameType, descriptionTimer, votingTimer, codenamesClueTimer, codenamesGuessTimer, enableMrWhite, t])

  return (
    <div className="rounded-xl border bg-card p-4">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full text-left"
      >
        <Settings className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold flex-1">{t("room.settings")}</h3>
        <span className="text-xs text-muted-foreground">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        <div className="mt-4 space-y-4">
          {gameType === "undercover" ? (
            <>
              {/* Description Timer */}
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                  {t("room.descriptionTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setDescriptionTimer(val)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                        descriptionTimer === val
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted hover:bg-muted/80"
                      }`}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Voting Timer */}
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                  {t("room.votingTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setVotingTimer(val)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                        votingTimer === val
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted hover:bg-muted/80"
                      }`}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Mr. White Toggle */}
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t("room.enableMrWhite")}
                  </label>
                  <button
                    type="button"
                    onClick={() => playerCount >= 4 && setEnableMrWhite(!enableMrWhite)}
                    disabled={playerCount < 4}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      enableMrWhite && playerCount >= 4 ? "bg-primary" : "bg-muted"
                    } ${playerCount < 4 ? "opacity-50 cursor-not-allowed" : ""}`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        enableMrWhite && playerCount >= 4 ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
                {playerCount < 4 && (
                  <p className="text-xs text-muted-foreground/70 mt-1">
                    {t("room.mrWhiteMinPlayers")}
                  </p>
                )}
              </div>
            </>
          ) : (
            <>
              {/* Clue Timer */}
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                  {t("room.clueTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setCodenamesClueTimer(val)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                        codenamesClueTimer === val
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted hover:bg-muted/80"
                      }`}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Guess Timer */}
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                  {t("room.guessTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setCodenamesGuessTimer(val)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                        codenamesGuessTimer === val
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted hover:bg-muted/80"
                      }`}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isSaving ? t("common.loading") : t("common.save")}
          </button>
        </div>
      )}
    </div>
  )
})
