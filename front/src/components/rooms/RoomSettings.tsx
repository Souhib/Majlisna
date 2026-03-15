import { ChevronDown, Settings } from "lucide-react"
import { memo, useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch } from "@/api/generated"
import { cn } from "@/lib/utils"

interface RoomSettingsProps {
  roomId: string
  settings: Record<string, unknown> | null
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz"
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
  const settingsMutation = useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch()

  const [descriptionTimer, setDescriptionTimer] = useState(0)
  const [votingTimer, setVotingTimer] = useState(0)
  const [codenamesClueTimer, setCodenamesClueTimer] = useState(0)
  const [codenamesGuessTimer, setCodenamesGuessTimer] = useState(0)
  const [enableMrWhite, setEnableMrWhite] = useState(true)
  const [wordQuizTurnDuration, setWordQuizTurnDuration] = useState(60)
  const [wordQuizRounds, setWordQuizRounds] = useState(7)
  const [wordQuizHintInterval, setWordQuizHintInterval] = useState(10)
  const [mcqQuizTurnDuration, setMcqQuizTurnDuration] = useState(15)
  const [mcqQuizRounds, setMcqQuizRounds] = useState(10)

  useEffect(() => {
    if (settings) {
      if (settings.description_timer !== undefined) setDescriptionTimer(settings.description_timer as number)
      if (settings.voting_timer !== undefined) setVotingTimer(settings.voting_timer as number)
      if (settings.codenames_clue_timer !== undefined) setCodenamesClueTimer(settings.codenames_clue_timer as number)
      if (settings.codenames_guess_timer !== undefined) setCodenamesGuessTimer(settings.codenames_guess_timer as number)
      if (settings.enable_mr_white !== undefined) setEnableMrWhite(settings.enable_mr_white as boolean)
      if (settings.word_quiz_turn_duration !== undefined) setWordQuizTurnDuration(settings.word_quiz_turn_duration as number)
      if (settings.word_quiz_rounds !== undefined) setWordQuizRounds(settings.word_quiz_rounds as number)
      if (settings.word_quiz_hint_interval !== undefined) setWordQuizHintInterval(settings.word_quiz_hint_interval as number)
      if (settings.mcq_quiz_turn_duration !== undefined) setMcqQuizTurnDuration(settings.mcq_quiz_turn_duration as number)
      if (settings.mcq_quiz_rounds !== undefined) setMcqQuizRounds(settings.mcq_quiz_rounds as number)
    }
  }, [settings])

  const timerLabel = (val: number) => (val === 0 ? t("room.noLimit") : `${val}s`)

  const isSaving = settingsMutation.isPending

  const handleSave = useCallback(async () => {
    try {
      const payload: Record<string, unknown> = {}
      if (gameType === "undercover") {
        payload.description_timer = descriptionTimer
        payload.voting_timer = votingTimer
        payload.enable_mr_white = enableMrWhite
      } else if (gameType === "codenames") {
        payload.codenames_clue_timer = codenamesClueTimer
        payload.codenames_guess_timer = codenamesGuessTimer
      } else if (gameType === "word_quiz") {
        payload.word_quiz_turn_duration = wordQuizTurnDuration
        payload.word_quiz_rounds = wordQuizRounds
        payload.word_quiz_hint_interval = wordQuizHintInterval
      } else if (gameType === "mcq_quiz") {
        payload.mcq_quiz_turn_duration = mcqQuizTurnDuration
        payload.mcq_quiz_rounds = mcqQuizRounds
      }
      await settingsMutation.mutateAsync({ room_id: roomId, data: payload })
      toast.success(t("room.settingsSaved"))
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to save settings"))
    }
  }, [roomId, gameType, descriptionTimer, votingTimer, codenamesClueTimer, codenamesGuessTimer, enableMrWhite, wordQuizTurnDuration, wordQuizRounds, wordQuizHintInterval, mcqQuizTurnDuration, mcqQuizRounds, t, settingsMutation])

  return (
    <div className="glass rounded-2xl p-5">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full text-left"
      >
        <Settings className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-bold flex-1">{t("room.settings")}</h3>
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform duration-200", isOpen && "rotate-180")} />
      </button>

      <div className={cn(
        "grid transition-all duration-300",
        isOpen ? "grid-rows-[1fr] opacity-100 mt-5" : "grid-rows-[0fr] opacity-0",
      )}>
        <div className="overflow-hidden space-y-5">
          {gameType === "undercover" ? (
            <>
              {/* Description Timer */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.descriptionTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setDescriptionTimer(val)}
                      className={cn(
                        "rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        descriptionTimer === val
                          ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm"
                          : "bg-muted/50 hover:bg-muted",
                      )}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Voting Timer */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.votingTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setVotingTimer(val)}
                      className={cn(
                        "rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        votingTimer === val
                          ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm"
                          : "bg-muted/50 hover:bg-muted",
                      )}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Mr. White Toggle */}
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-muted-foreground">
                    {t("room.enableMrWhite")}
                  </label>
                  <button
                    type="button"
                    onClick={() => playerCount >= 4 && setEnableMrWhite(!enableMrWhite)}
                    disabled={playerCount < 4}
                    className={cn(
                      "relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-200",
                      enableMrWhite && playerCount >= 4 ? "bg-gradient-to-r from-primary to-primary/90" : "bg-muted",
                      playerCount < 4 && "opacity-50 cursor-not-allowed",
                    )}
                  >
                    <span
                      className={cn(
                        "inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200",
                        enableMrWhite && playerCount >= 4 ? "translate-x-6" : "translate-x-1",
                      )}
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
          ) : gameType === "codenames" ? (
            <>
              {/* Clue Timer */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.clueTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setCodenamesClueTimer(val)}
                      className={cn(
                        "rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        codenamesClueTimer === val
                          ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm"
                          : "bg-muted/50 hover:bg-muted",
                      )}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Guess Timer */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.guessTimer")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {TIMER_OPTIONS.map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setCodenamesGuessTimer(val)}
                      className={cn(
                        "rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        codenamesGuessTimer === val
                          ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm"
                          : "bg-muted/50 hover:bg-muted",
                      )}
                    >
                      {timerLabel(val)}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : gameType === "word_quiz" ? (
            <>
              {/* Turn Duration */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.wordQuizTurnDuration")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {[30, 45, 60, 90, 120, 180].map((val) => (
                    <button key={val} type="button" onClick={() => setWordQuizTurnDuration(val)}
                      className={cn("rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        wordQuizTurnDuration === val ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm" : "bg-muted/50 hover:bg-muted")}>
                      {val}s
                    </button>
                  ))}
                </div>
              </div>
              {/* Number of Rounds */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.wordQuizRounds")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {[3, 5, 7, 10, 15, 20].map((val) => (
                    <button key={val} type="button" onClick={() => setWordQuizRounds(val)}
                      className={cn("rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        wordQuizRounds === val ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm" : "bg-muted/50 hover:bg-muted")}>
                      {val}
                    </button>
                  ))}
                </div>
              </div>
              {/* Hint Interval */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.wordQuizHintInterval")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {[5, 10, 15, 20, 30].map((val) => (
                    <button key={val} type="button" onClick={() => setWordQuizHintInterval(val)}
                      className={cn("rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        wordQuizHintInterval === val ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm" : "bg-muted/50 hover:bg-muted")}>
                      {val}s
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* MCQ Quiz — Time per question */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.mcqQuizTurnDuration")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {[10, 15, 20, 30, 45, 60].map((val) => (
                    <button key={val} type="button" onClick={() => setMcqQuizTurnDuration(val)}
                      className={cn("rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        mcqQuizTurnDuration === val ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm" : "bg-muted/50 hover:bg-muted")}>
                      {val}s
                    </button>
                  ))}
                </div>
              </div>
              {/* MCQ Quiz — Number of questions */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground block mb-2">
                  {t("room.mcqQuizRounds")}
                </label>
                <div className="flex gap-1.5 flex-wrap">
                  {[5, 10, 15, 20, 30].map((val) => (
                    <button key={val} type="button" onClick={() => setMcqQuizRounds(val)}
                      className={cn("rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200",
                        mcqQuizRounds === val ? "bg-gradient-to-r from-primary to-primary/90 text-primary-foreground shadow-sm" : "bg-muted/50 hover:bg-muted")}>
                      {val}
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
            className="w-full rounded-xl bg-gradient-to-r from-primary to-primary/90 px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 hover:shadow-lg disabled:opacity-50 transition-all duration-200"
          >
            {isSaving ? t("common.loading") : t("common.save")}
          </button>
        </div>
      </div>
    </div>
  )
})
