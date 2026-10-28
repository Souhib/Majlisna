import { memo } from "react"
import { useTranslation } from "react-i18next"
import { BusyLozenges } from "@/components/ui/button"
import { guessStatus, isArabicScript, type CodenamesTurn } from "./model"

interface ClueBannerProps {
  turn: Pick<CodenamesTurn, "clue_word" | "clue_number" | "guesses_made">
  /** The spymaster who gave (or is choosing) the clue. */
  spymasterName?: string | null
  /** Operatives of the current team, and how many are pointing at a card now. */
  pointing?: { current: number; total: number } | null
}

/**
 * The clue on the table (sketch C): "Clue from Yusuf / KNOWLEDGE 2 / 1 guess made,
 * 1 left, plus a bonus". Before the clue: who is choosing it. A clue written in Arabic
 * is set in the hand (Aref Ruqaa); a Latin one in Marcellus capitals.
 */
export const ClueBanner = memo(function ClueBanner({ turn, spymasterName, pointing }: ClueBannerProps) {
  const { t } = useTranslation()

  if (!turn.clue_word) {
    return (
      <div className="cn-clue" data-waiting="true">
        <BusyLozenges className="text-brass" />
        <p className="text-[14px] text-muted-foreground">
          {spymasterName ? t("game.codenames.choosingClue", { name: spymasterName }) : t("game.codenames.waitingForClue")}
        </p>
      </div>
    )
  }

  const status = guessStatus(turn)
  const arabic = isArabicScript(turn.clue_word)
  let rest: string
  if (status.unlimited) rest = t("game.codenames.noLimitLeft")
  else if (status.left > 0) rest = t("game.codenames.leftPlusBonus", { count: status.left })
  else rest = t("game.codenames.bonusLeft")

  return (
    <div className="cn-clue">
      <div className="min-w-0">
        <p className="text-[13px] leading-tight text-muted-foreground">
          {spymasterName ? t("game.codenames.clueFrom", { name: spymasterName }) : t("game.codenames.clue")}
        </p>
        <p className="mt-1 flex items-baseline gap-3.5">
          <span className="cn-clue-word" data-script={arabic ? "ar" : "lat"} lang={arabic ? "ar" : undefined} dir="auto">
            {turn.clue_word}
          </span>
          <span className="cn-clue-n" aria-hidden={status.unlimited || undefined}>
            {status.unlimited ? "∞" : turn.clue_number}
          </span>
          {status.unlimited ? <span className="sr-only">{t("game.codenames.composer.unlimited")}</span> : null}
        </p>
      </div>
      <p className="cn-clue-rest">
        <span className="block num">{t("game.codenames.guessesMade", { count: status.made })}</span>
        <span className="block num">{rest}</span>
        {pointing && pointing.total > 1 && pointing.current > 0 ? (
          <span className="block num text-foreground">{t("game.codenames.pointingProgress", { current: pointing.current, total: pointing.total })}</span>
        ) : null}
      </p>
    </div>
  )
})
