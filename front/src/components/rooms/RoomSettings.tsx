import { ChevronDown, SlidersHorizontal } from "lucide-react"
import { memo, useCallback, useEffect, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch } from "@/api/generated"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { Switch } from "@/components/ui/switch"
import { roomErrorMessage } from "./errors"
import { cn } from "@/lib/utils"
import { GAME_NAME_KEY, type GameType } from "./lobby"

interface RoomSettingsProps {
  roomId: string
  settings: Record<string, unknown> | null
  gameType: GameType
  playerCount: number
  className?: string
}

const TIMER_OPTIONS = [0, 15, 30, 45, 60, 90, 120, 180]
// Mirrors UNDERCOVER_MR_WHITE_MIN_PLAYERS: below 5, one undercover plus one Mr. White
// already tie the civilians, and the impostors win at parity.
export const MR_WHITE_MIN_PLAYERS = 5
const DIFFICULTIES = ["mixed", "easy", "medium", "hard"] as const

interface Option<T> {
  value: T
  label: string
}

/**
 * One setting: a row of chips that are native radio buttons underneath (one tab stop,
 * arrow keys move the choice, the legend names the group). The chosen chip takes the
 * primary fill; figures are tabular.
 */
function OptionGroup<T extends string | number>({
  legend,
  value,
  options,
  onChange,
}: {
  legend: string
  value: T
  options: Option<T>[]
  onChange: (value: T) => void
}) {
  const name = useId()
  return (
    <fieldset className="grid gap-2">
      <legend className="type-label mb-2">{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <label key={String(o.value)} className="relative cursor-pointer">
            <input type="radio" name={name} className="peer sr-only" checked={value === o.value} onChange={() => onChange(o.value)} />
            <span
              className={cn(
                "inline-flex h-10 min-w-12 items-center justify-center rounded-sm border border-line bg-surface px-3 text-[14px] font-medium leading-none text-muted-foreground num pointer-coarse:h-11",
                "transition-[background-color,border-color,color] duration-(--dur-state) ease-out hover:border-line-brass-strong hover:text-foreground",
                "peer-checked:border-primary peer-checked:bg-primary peer-checked:text-primary-foreground",
                "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus",
              )}
            >
              {o.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

/**
 * The host's settings for the game chosen in the lobby: a hairline panel that opens from
 * its header. Values come from the room and are saved explicitly.
 */
export const RoomSettings = memo(function RoomSettings({ roomId, settings, gameType, playerCount, className }: RoomSettingsProps) {
  const { t } = useTranslation()
  const uid = useId()
  const bodyId = `${uid}-body`
  const mrWhiteId = `${uid}-mr-white`
  const mrWhiteHintId = `${uid}-mr-white-hint`
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
  const [wordQuizDifficulty, setWordQuizDifficulty] = useState("mixed")
  const [mcqQuizDifficulty, setMcqQuizDifficulty] = useState("mixed")

  // Every room_state push carries a NEW settings object, so syncing on the object reset
  // the host's unsaved choices whenever anyone joined or reconnected. Sync on the values.
  const settingsKey = settings ? JSON.stringify(settings) : ""
  useEffect(() => {
    if (!settings) return
    if (settings.description_timer != null) setDescriptionTimer(settings.description_timer as number)
    if (settings.voting_timer != null) setVotingTimer(settings.voting_timer as number)
    if (settings.codenames_clue_timer != null) setCodenamesClueTimer(settings.codenames_clue_timer as number)
    if (settings.codenames_guess_timer != null) setCodenamesGuessTimer(settings.codenames_guess_timer as number)
    if (settings.enable_mr_white != null) setEnableMrWhite(settings.enable_mr_white as boolean)
    if (settings.word_quiz_turn_duration != null) setWordQuizTurnDuration(settings.word_quiz_turn_duration as number)
    if (settings.word_quiz_rounds != null) setWordQuizRounds(settings.word_quiz_rounds as number)
    if (settings.word_quiz_hint_interval != null) setWordQuizHintInterval(settings.word_quiz_hint_interval as number)
    if (settings.mcq_quiz_turn_duration != null) setMcqQuizTurnDuration(settings.mcq_quiz_turn_duration as number)
    if (settings.mcq_quiz_rounds != null) setMcqQuizRounds(settings.mcq_quiz_rounds as number)
    if (settings.word_quiz_difficulty != null) setWordQuizDifficulty(settings.word_quiz_difficulty as string)
    if (settings.mcq_quiz_difficulty != null) setMcqQuizDifficulty(settings.mcq_quiz_difficulty as string)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the values, see above
  }, [settingsKey])

  const seconds = (val: number) => (val === 0 ? t("room.noLimit") : t("room.settingsPanel.seconds", { count: val }))
  const timerOptions = TIMER_OPTIONS.map((v) => ({ value: v, label: seconds(v) }))
  const secondsOptions = (values: number[]) => values.map((v) => ({ value: v, label: seconds(v) }))
  const countOptions = (values: number[]) => values.map((v) => ({ value: v, label: String(v) }))
  const difficultyOptions = DIFFICULTIES.map((v) => ({
    value: v as string,
    label: t(`room.difficulty${v.charAt(0).toUpperCase() + v.slice(1)}`),
  }))

  const mrWhitePossible = playerCount >= MR_WHITE_MIN_PLAYERS
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
        payload.word_quiz_difficulty = wordQuizDifficulty
      } else if (gameType === "mcq_quiz") {
        payload.mcq_quiz_turn_duration = mcqQuizTurnDuration
        payload.mcq_quiz_rounds = mcqQuizRounds
        payload.mcq_quiz_difficulty = mcqQuizDifficulty
      }
      await settingsMutation.mutateAsync({ room_id: roomId, data: payload })
      toast.success(t("room.settingsSaved"))
    } catch (err) {
      toast.error(roomErrorMessage(err, t("room.settingsPanel.saveFailed")))
    }
  }, [
    roomId,
    gameType,
    descriptionTimer,
    votingTimer,
    codenamesClueTimer,
    codenamesGuessTimer,
    enableMrWhite,
    wordQuizTurnDuration,
    wordQuizRounds,
    wordQuizHintInterval,
    wordQuizDifficulty,
    mcqQuizTurnDuration,
    mcqQuizRounds,
    mcqQuizDifficulty,
    t,
    settingsMutation,
  ])

  return (
    <Panel flush className={cn("overflow-hidden", className)}>
      <h2 className="type-panel">
        <button
          type="button"
          onClick={() => setIsOpen((open) => !open)}
          aria-expanded={isOpen}
          aria-controls={bodyId}
          className="flex min-h-12 w-full cursor-pointer items-center gap-3 px-4 py-3 text-start transition-colors duration-(--dur-state) hover:bg-[color-mix(in_oklch,var(--brass)_6%,transparent)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus sm:px-5"
        >
          <SlidersHorizontal className="size-[18px] shrink-0 text-brass" aria-hidden="true" />
          <span>{t("room.settingsPanel.title", { game: t(GAME_NAME_KEY[gameType]) })}</span>
          <ChevronDown
            className={cn(
              "ms-auto size-4 shrink-0 text-muted-foreground transition-transform duration-(--dur-state) motion-reduce:transition-none",
              isOpen && "rotate-180",
            )}
            aria-hidden="true"
          />
        </button>
      </h2>

      {isOpen ? (
        <div id={bodyId} className="grid gap-5 border-t border-line p-4 sm:p-5">
          {gameType === "undercover" ? (
            <>
              <OptionGroup legend={t("room.settingsPanel.descriptionTimer")} value={descriptionTimer} options={timerOptions} onChange={setDescriptionTimer} />
              <OptionGroup legend={t("room.settingsPanel.votingTimer")} value={votingTimer} options={timerOptions} onChange={setVotingTimer} />
              <div className="grid gap-1.5">
                <div className="flex items-center justify-between gap-4">
                  <label htmlFor={mrWhiteId} className="text-[15px] leading-snug text-foreground">
                    {t("room.enableMrWhite")}
                  </label>
                  <Switch
                    id={mrWhiteId}
                    checked={enableMrWhite && mrWhitePossible}
                    disabled={!mrWhitePossible}
                    onCheckedChange={setEnableMrWhite}
                    aria-describedby={mrWhitePossible ? undefined : mrWhiteHintId}
                  />
                </div>
                {!mrWhitePossible && (
                  <p id={mrWhiteHintId} className="text-[13px] leading-[1.45] text-muted-foreground">
                    {t("room.mrWhiteMinPlayers")}
                  </p>
                )}
              </div>
            </>
          ) : gameType === "codenames" ? (
            <>
              <OptionGroup legend={t("room.settingsPanel.clueTimer")} value={codenamesClueTimer} options={timerOptions} onChange={setCodenamesClueTimer} />
              <OptionGroup legend={t("room.settingsPanel.guessTimer")} value={codenamesGuessTimer} options={timerOptions} onChange={setCodenamesGuessTimer} />
            </>
          ) : gameType === "word_quiz" ? (
            <>
              <OptionGroup legend={t("room.difficulty")} value={wordQuizDifficulty} options={difficultyOptions} onChange={setWordQuizDifficulty} />
              <OptionGroup
                legend={t("room.settingsPanel.wordQuizTurn")}
                value={wordQuizTurnDuration}
                options={secondsOptions([30, 45, 60, 90, 120, 180])}
                onChange={setWordQuizTurnDuration}
              />
              <OptionGroup
                legend={t("room.settingsPanel.wordQuizRounds")}
                value={wordQuizRounds}
                options={countOptions([3, 5, 7, 10, 15, 20])}
                onChange={setWordQuizRounds}
              />
              <OptionGroup
                legend={t("room.settingsPanel.wordQuizHintInterval")}
                value={wordQuizHintInterval}
                options={secondsOptions([5, 10, 15, 20, 30])}
                onChange={setWordQuizHintInterval}
              />
            </>
          ) : (
            <>
              <OptionGroup legend={t("room.difficulty")} value={mcqQuizDifficulty} options={difficultyOptions} onChange={setMcqQuizDifficulty} />
              <OptionGroup
                legend={t("room.settingsPanel.mcqQuizTurn")}
                value={mcqQuizTurnDuration}
                options={secondsOptions([10, 15, 20, 30, 45, 60])}
                onChange={setMcqQuizTurnDuration}
              />
              <OptionGroup
                legend={t("room.settingsPanel.mcqQuizRounds")}
                value={mcqQuizRounds}
                options={countOptions([5, 10, 15, 20, 30])}
                onChange={setMcqQuizRounds}
              />
            </>
          )}

          <Button variant="secondary" onClick={handleSave} loading={isSaving} className="w-full sm:w-auto sm:justify-self-start">
            {t("common.save")}
          </Button>
        </div>
      ) : null}
    </Panel>
  )
})
