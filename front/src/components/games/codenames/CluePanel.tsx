import { memo, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"

interface CluePanelProps {
  clueWord: string
  clueNumber: number
  isSubmitting: boolean
  onClueWordChange: (value: string) => void
  onClueNumberChange: (value: number) => void
  onSubmit: () => void
}

/** The counts a spymaster can give: 1–4 and "no limit" (0 on the wire). */
export const CLUE_COUNTS = [1, 2, 3, 4, 0] as const

/**
 * The spymaster's composer (sketch D): one word, how many cards it covers (1–4 or no
 * limit), "Give clue". Under the board, so the key stays in view while typing.
 */
export const CluePanel = memo(function CluePanel({
  clueWord,
  clueNumber,
  isSubmitting,
  onClueWordChange,
  onClueNumberChange,
  onSubmit,
}: CluePanelProps) {
  const { t } = useTranslation()
  const empty = !clueWord.trim()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (empty || isSubmitting) return
    onSubmit()
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 grid gap-3" aria-label={t("game.codenames.giveClue")}>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
        <Field label={t("game.codenames.composer.label")} hideLabel hint={t("game.codenames.composer.hint")}>
          <Input
            value={clueWord}
            onChange={(e) => onClueWordChange(e.target.value)}
            placeholder={t("game.codenames.cluePlaceholder")}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            enterKeyHint="send"
            maxLength={50}
            dir="auto"
          />
        </Field>
        <Button type="submit" loading={isSubmitting} disabled={empty && !isSubmitting}>
          {t("game.codenames.composer.give")}
        </Button>
      </div>
      <div>
        <p id="cn-count-label" className="type-label mb-1.5">
          {t("game.codenames.composer.count")}
        </p>
        <div className="cn-count" role="group" aria-labelledby="cn-count-label">
          {CLUE_COUNTS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={clueNumber === n}
              aria-label={n === 0 ? t("game.codenames.composer.unlimited") : undefined}
              onClick={() => onClueNumberChange(n)}
            >
              {n === 0 ? <span aria-hidden="true">∞</span> : n}
            </button>
          ))}
        </div>
      </div>
    </form>
  )
})

interface ClueAnnouncerProps {
  /** The clue on the table, or nothing while the spymaster is choosing. */
  clueWord?: string | null
  clueNumber?: number | null
  /** The team the clue is for, as `game.codenames.teams` names it (Red / Blue). */
  teamName: string
}

/**
 * Reads a clue out once, when it lands on the table. The header's live line only says
 * whose turn it is ("Your turn to guess"), never the word, so a player on a screen
 * reader learned the clue by going to look for it. Mount it once on the page, whatever
 * the player's role: it is always in the DOM (a live region inserted together with its
 * text is not read), its text changes only when a new clue arrives, and an unchanged
 * text is never read twice.
 */
export function ClueAnnouncer({ clueWord, clueNumber, teamName }: ClueAnnouncerProps) {
  const { t } = useTranslation()
  const word = clueWord?.trim()
  const number = clueNumber === 0 ? t("game.codenames.composer.unlimited") : (clueNumber ?? "")
  return (
    <p className="sr-only" role="status" aria-atomic="true">
      {word ? t("game.codenames.clueAnnounce", { team: teamName, word, number }) : ""}
    </p>
  )
}
