import { memo } from "react"
import { useTranslation } from "react-i18next"
import { TeamGlyph } from "@/components/brand"
import { Panel, PanelHeader } from "@/components/ui/panel"
import { cn } from "@/lib/utils"
import { arabicForm, cardGlyph, type ClueHistoryEntry, isArabicScript, teamWool } from "./model"

interface ClueHistoryProps {
  history: ClueHistoryEntry[]
}

/**
 * The clues given so far, newest first: the team (glyph), the clue and its count, then
 * each card it turned with the glyph of what the card turned out to be. A miss is
 * muted and named for assistive tech; nothing is struck through (a word may be a
 * sacred name).
 */
export const ClueHistory = memo(function ClueHistory({ history }: ClueHistoryProps) {
  const { t, i18n } = useTranslation()
  const arabicUi = (i18n.language ?? "").startsWith("ar")

  if (history.length === 0) return null

  return (
    <Panel aria-labelledby="cn-history-title">
      <PanelHeader title={<span id="cn-history-title">{t("game.codenames.clueHistory")}</span>} titleAs="h2" className="mb-2" />
      <ol>
        {[...history].reverse().map((entry, i) => {
          const arabic = isArabicScript(entry.clue_word)
          return (
            <li key={history.length - i} className="border-b border-line py-3 last:border-b-0" data-testid="clue-history-entry">
              <p className="flex items-baseline gap-2.5">
                <TeamGlyph team={teamWool(entry.team)} className="translate-y-px self-center text-muted-foreground" />
                <span className="sr-only">{t(`game.codenames.teams.${entry.team}`)}: </span>
                <span
                  className={cn(
                    "min-w-0 wrap-anywhere",
                    arabic ? "font-hand text-[19px] leading-snug" : "font-display text-[17px] uppercase tracking-[0.06em]",
                  )}
                  lang={arabic ? "ar" : undefined}
                  dir="auto"
                >
                  {entry.clue_word}
                </span>
                <span className="num font-semibold text-brass">
                  {entry.clue_number === 0 ? (
                    <>
                      <span aria-hidden="true">∞</span>
                      <span className="sr-only">{t("game.codenames.composer.unlimited")}</span>
                    </>
                  ) : (
                    entry.clue_number
                  )}
                </span>
              </p>
              {entry.guesses.length > 0 ? (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {entry.guesses.map((guess, j) => {
                    const glyph = cardGlyph(guess.card_type)
                    const ar = arabicForm(guess)
                    const shown = arabicUi && ar ? ar : guess.word
                    return (
                      <li
                        key={j}
                        className={cn(
                          "inline-flex h-7 items-center gap-1.5 rounded-sm border px-2 text-[13px] leading-none",
                          guess.correct ? "border-line bg-surface-2 text-foreground" : "border-dashed border-line text-muted-foreground",
                        )}
                      >
                        {glyph ? <TeamGlyph team={glyph} size={10} /> : null}
                        <span lang={arabicUi && ar ? "ar" : undefined} className={arabicUi && ar ? "font-nass text-[15px]" : undefined}>
                          {shown}
                        </span>
                        <span className="sr-only">
                          {" "}
                          ({guess.correct ? t("game.codenames.correct") : t("game.codenames.wrong")})
                        </span>
                      </li>
                    )
                  })}
                </ul>
              ) : null}
            </li>
          )
        })}
      </ol>
    </Panel>
  )
})
