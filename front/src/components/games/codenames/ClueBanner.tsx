import { memo, type RefObject, useEffect, useLayoutEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { currentLanguage } from "@/components/layout/language-switch"
import { BusyLozenges } from "@/components/ui/button"
import { bezier, dur, ease, inkDuration } from "@/lib/motion"
import { holdsSacredName } from "@/lib/sacred-names"
import { CLUE_COUNTS, clueJustLanded, clueKey } from "./CluePanel"
import { guessStatus, isArabicScript, type CodenamesTurn } from "./model"

interface ClueBannerProps {
  turn: Pick<CodenamesTurn, "clue_word" | "clue_number" | "guesses_made">
  /** The spymaster who gave (or is choosing) the clue. */
  spymasterName?: string | null
  /** Operatives of the current team, and how many are pointing at a card now. */
  pointing?: { current: number; total: number } | null
}

/** A lozenge stamped: the CSS `loz-stamp` (index.css), 220 ms on `--ease-press`. */
export const CLUE_STAMP_MS = 220
/** Reduced motion: the clue line fades in, as the reduced `ink` does (index.css), in 140 ms. */
export const CLUE_REDUCED_FADE_MS = 140

/** The most lozenges a count draws: the composer's 1–4. Beyond (only the API sends it), the figure says it alone. */
const MOST_LOZENGES = Math.max(...CLUE_COUNTS)

/** `loz-stamp` as keyframes: from 1.6 and unseen, through 0.92 at 60 %, to rest (no overshoot past 1 at the end). */
const STAMP: Keyframe[] = [
  { transform: "scale(1.6)", opacity: 0 },
  { transform: "scale(0.92)", opacity: 1, offset: 0.6 },
  { transform: "scale(1)", opacity: 1 },
]

/** Hebrew, Arabic, Syriac, Thaana, NKo… and the Hebrew and Arabic presentation forms. */
const RTL_LETTER = /[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]/
const LETTER = /\p{L}/u

/** Whether a word reads right to left: its first strong letter decides, as `dir="auto"` does. */
export function writesRightToLeft(word: string): boolean {
  for (const char of word) {
    if (RTL_LETTER.test(char)) return true
    if (LETTER.test(char)) return false
  }
  return false
}

/**
 * The faces a clue is set in (`.cn-clue-word`): Marcellus for a Latin clue (14 kB), the hand for
 * an Arabic one (46 kB), asked for only in the Arabic interface, where a clue is most likely
 * Arabic. A phone has neither before its first clue (its cards are set in other faces), so the
 * clue was written in a fallback that swapped under the pen, and the count jumped sideways.
 * Asked for while the spymaster chooses: the files the clue would fetch a moment later.
 */
const CLUE_FACE = { ar: ['700 1em "Aref Ruqaa"', "ب"], lat: ["400 1em Marcellus", "A"] } as const

function warmClueFaces(arabicUi: boolean) {
  const fonts = typeof document !== "undefined" ? document.fonts : undefined
  if (typeof fonts?.load !== "function") return
  for (const [font, sample] of arabicUi ? [CLUE_FACE.ar, CLUE_FACE.lat] : [CLUE_FACE.lat]) {
    // a face that cannot be fetched now is fetched again by the clue itself: nothing to report
    fonts.load(font, sample).catch(() => undefined)
  }
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

/**
 * What the count stamps: its lozenges where the banner shows them (codenames.css hides them on
 * a banner too narrow for them, a phone's), else the figure itself, once.
 */
function stampsOf(line: HTMLElement): HTMLElement[] {
  const lozenges = line.querySelector<HTMLElement>(".cn-clue-loz")
  if (lozenges && getComputedStyle(lozenges).display !== "none") return [...lozenges.querySelectorAll<HTMLElement>(":scope > i")]
  const figure = line.querySelector<HTMLElement>(".cn-clue-n")
  return figure ? [figure] : []
}

/**
 * The qalam on the compositor. The `ink` utility sweeps a mask by a registered custom property,
 * which repaints every frame; here the word is uncovered by translation alone: the pen (a box
 * with a soft edge at its reading end, a static mask) travels in from one full length before
 * the reading start while the ink inside it travels the other way on the same clock, so the
 * letters stand still and the pen's edge writes them. Then the count is stamped, a lozenge
 * --dur-tap after the other (the figure itself where there are no lozenges). Nothing waits
 * hidden once its time is over: no fill holds a frame, and the stamps fill backwards only
 * while they wait for their turn.
 *
 * A clue is the spymaster's free text and may be a sacred name (the server refuses only a
 * card's own word): nothing ever passes over one (DESIGN.md §7), so such a word is not
 * written but fades in (--dur-state, on --ease-out), and its count is stamped after it.
 */
function writeClueIn(line: HTMLElement, word: string): Animation[] {
  if (typeof line.animate !== "function") return []
  if (prefersReducedMotion()) {
    const fade = line.animate([{ opacity: 0 }, { opacity: 1 }], { duration: CLUE_REDUCED_FADE_MS, easing: "linear" })
    fade.id = "clue-ink"
    return [fade]
  }
  const pen = line.querySelector<HTMLElement>(".cn-clue-pen")
  const ink = line.querySelector<HTMLElement>(".cn-clue-ink")
  if (!pen || !ink) return []
  let writing: number
  let runs: Animation[]
  if (holdsSacredName(word)) {
    writing = dur.state * 1000
    runs = [ink.animate([{ opacity: 0 }, { opacity: 1 }], { duration: writing, easing: bezier(ease.out) })]
  } else {
    writing = inkDuration(word) * 1000
    const from = writesRightToLeft(word) ? 100 : -100
    const timing = { duration: writing, easing: bezier(ease.ink) }
    runs = [
      pen.animate([{ transform: `translateX(${from}%)` }, { transform: "translateX(0%)" }], timing),
      ink.animate([{ transform: `translateX(${-from}%)` }, { transform: "translateX(0%)" }], timing),
    ]
  }
  for (const run of runs) run.id = "clue-ink"
  stampsOf(line).forEach((el, i) => {
    const stamp = el.animate(STAMP, { duration: CLUE_STAMP_MS, easing: bezier(ease.press), delay: writing + i * dur.tap * 1000, fill: "backwards" })
    stamp.id = "clue-stamp"
    runs.push(stamp)
  })
  return runs
}

/**
 * Writes a clue in when it is NEW on the table: a clue after none or after another one, or the
 * one the announcer has just seen land (the spymaster's banner mounts with their own clue).
 * Never the clue a page opens or reloads on, never a refetch or a socket push of the same clue.
 * A layout effect, so the first painted frame is already the animation's first.
 */
function useClueWriting(lineRef: RefObject<HTMLParagraphElement | null>, key: string | null, word: string) {
  const shown = useRef(key)
  useLayoutEffect(() => {
    const previous = shown.current
    shown.current = key
    const line = lineRef.current
    if (key === null || !line || (previous === key && !clueJustLanded(key))) return
    const runs = writeClueIn(line, word)
    return () => {
      for (const run of runs) run.cancel()
    }
  }, [key, word, lineRef])
}

/**
 * The clue on the table (sketch C): "Clue from Yusuf / KNOWLEDGE 2 ◆◆ / 1 guess made,
 * 1 left, plus a bonus". Before the clue: who is choosing it. A clue written in Arabic
 * is set in the hand (Aref Ruqaa); a Latin one in Marcellus capitals. The count is its figure
 * and as many brass lozenges (for the eye; the figure is what is read), on a banner wide enough
 * for them: a phone's shows the figure alone.
 *
 * A new clue is written in, in its own reading direction, then its count is stamped
 * (`useClueWriting`); a clue that is a sacred name fades in instead (`holdsSacredName`). The
 * word, the figure and the lozenges are in the DOM from the first frame, and only `transform`
 * and `opacity` move.
 *
 * The banner holds the clue's height while it waits (`.cn-clue`'s min-height in
 * codenames.css), so the board under the operatives' fingers does not move when the clue
 * lands. Keep that reservation in step if a line is added here.
 */
export const ClueBanner = memo(function ClueBanner({ turn, spymasterName, pointing }: ClueBannerProps) {
  const { t, i18n } = useTranslation()
  const lineRef = useRef<HTMLParagraphElement>(null)
  const word = turn.clue_word ?? ""
  useClueWriting(lineRef, clueKey(turn.clue_word, turn.clue_number), word)
  const waiting = !turn.clue_word
  const arabicUi = currentLanguage(i18n.language) === "ar"
  useEffect(() => {
    if (waiting) warmClueFaces(arabicUi)
  }, [waiting, arabicUi])

  // The two states' lines carry keys: the waiting line is not the clue's count column, and a
  // reused node would be reported as a layout shift when the clue lands.
  if (!turn.clue_word) {
    return (
      <div className="cn-clue" data-waiting="true">
        <BusyLozenges className="text-brass" />
        <p key="choosing" className="text-[14px] text-muted-foreground">
          {spymasterName ? t("game.codenames.choosingClue", { name: spymasterName }) : t("game.codenames.waitingForClue")}
        </p>
      </div>
    )
  }

  const status = guessStatus(turn)
  const arabic = isArabicScript(word)
  const lozenges = status.unlimited || turn.clue_number > MOST_LOZENGES ? 0 : turn.clue_number
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
        <p ref={lineRef} className="cn-clue-line mt-1 flex items-baseline gap-3.5">
          <span className="cn-clue-word" data-script={arabic ? "ar" : "lat"} lang={arabic ? "ar" : undefined} dir="auto">
            <span className="cn-clue-pen" data-dir={writesRightToLeft(word) ? "rtl" : "ltr"}>
              <span className="cn-clue-ink">{word}</span>
            </span>
          </span>
          <span className="cn-clue-count">
            <span className="cn-clue-n" aria-hidden={status.unlimited || undefined}>
              {status.unlimited ? "∞" : turn.clue_number}
            </span>
            {lozenges > 0 ? (
              <span className="cn-clue-loz" aria-hidden="true">
                {Array.from({ length: lozenges }, (_, i) => (
                  <i key={i} />
                ))}
              </span>
            ) : null}
          </span>
          {status.unlimited ? <span className="sr-only">{t("game.codenames.composer.unlimited")}</span> : null}
        </p>
      </div>
      <p key="rest" className="cn-clue-rest">
        <span className="block num">{t("game.codenames.guessesMade", { count: status.made })}</span>
        <span className="block num">{rest}</span>
        {pointing && pointing.total > 1 && pointing.current > 0 ? (
          <span className="block num text-foreground">{t("game.codenames.pointingProgress", { current: pointing.current, total: pointing.total })}</span>
        ) : null}
      </p>
    </div>
  )
})
