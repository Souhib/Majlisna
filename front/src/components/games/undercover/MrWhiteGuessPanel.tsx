import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"
import { Verdict, type VerdictRound } from "./Verdict"

interface MrWhiteGuessPanelProps {
  isGuesser: boolean
  /** The round that found Mr. White (its vote_history entry). */
  round?: VerdictRound | null
  currentUserId?: string
  guess: string
  isSubmitting: boolean
  onGuessChange: (value: string) => void
  onSubmit: () => void
}

/**
 * The eliminated Mr. White's last chance: one guess at the civilians' word. Everyone else
 * sees his tablet turned over (a dashed page: he had no word) while he guesses.
 */
export const MrWhiteGuessPanel = memo(function MrWhiteGuessPanel({
  isGuesser,
  round,
  currentUserId,
  guess,
  isSubmitting,
  onGuessChange,
  onSubmit,
}: MrWhiteGuessPanelProps) {
  const { t } = useTranslation()

  if (!isGuesser) {
    const waiting = (
      <div className="grid gap-1" aria-live="polite">
        <p className="text-[16px] font-medium">{t("game.undercover.mrWhiteIsGuessingTitle")}</p>
        <p className="text-[14.5px] leading-normal text-muted-foreground">{t("game.undercover.mrWhiteIsGuessing")}</p>
      </div>
    )
    if (round?.eliminated) {
      // compact: the player's own tablet stands beside it and carries the screen's band
      return <Verdict compact testId="elimination-overlay" round={round} currentUserId={currentUserId} action={waiting} />
    }
    return (
      <section data-testid="elimination-overlay" className="grid gap-2" aria-live="polite">
        <h2 className="type-title text-[26px] sm:text-[30px]">{t("game.undercover.mrWhiteIsGuessingTitle")}</h2>
        <p className="text-[15px] leading-normal text-muted-foreground">{t("game.undercover.mrWhiteIsGuessing")}</p>
      </section>
    )
  }

  return (
    <section data-testid="elimination-overlay" aria-labelledby="uc-guess-title" className="grid gap-5">
      <div>
        <h2 id="uc-guess-title" className="type-title text-[26px] sm:text-[30px]">
          {t("game.undercover.mrWhiteGuessTitle")}
        </h2>
        <p className="mt-1.5 max-w-[52ch] text-[15px] leading-normal text-muted-foreground">{t("game.undercover.mrWhiteGuessPrompt")}</p>
      </div>
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        <Field id="mr-white-guess-input" label={t("game.undercover.mrWhiteGuessPlaceholder")} hint={t("game.undercover.mrWhiteGuessHint")}>
          <div className="flex gap-2.5">
            <Input
              value={guess}
              onChange={(e) => onGuessChange(e.target.value)}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              // the guesser lands here on purpose: the phase exists only for this field
              autoFocus
              maxLength={50}
              className="min-w-0 flex-1"
            />
            <Button type="submit" loading={isSubmitting} disabled={!guess.trim()}>
              {t("game.undercover.mrWhiteGuessSubmit")}
            </Button>
          </div>
        </Field>
      </form>
    </section>
  )
})
