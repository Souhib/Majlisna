import { type QueryKey } from "@tanstack/react-query"
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { getRoomRiddleApiV1RoomsRoomIdRiddleGetQueryKey, type RoomRiddle, useGetRoomRiddleApiV1RoomsRoomIdRiddleGet } from "@/api/generated"
import { currentLanguage } from "@/components/layout/language-switch"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { dur, ease, inkDuration } from "@/lib/motion"
import { holdsSacredName } from "@/lib/sacred-names"
import { cn } from "@/lib/utils"
import { RIDDLE_REVEAL_AFTER_MS, type RiddleRecord, readRiddleRecord, riddleAskKey, settleRiddleRecord, writeRiddleRecord } from "./samar-riddle"

/** The `id` of the line's writing (its two transforms, or its fade). */
export const RIDDLE_INK_ID = "samar-riddle"
/** The `id` of the answer's and the offer's fades. */
const RIDDLE_FADE_ID = "samar-riddle-fade"

/** The qalam's soft edge: the writing window runs this far past the line, clipped. */
const FEATHER_EM = 1.25

const NOTE_KEY = {
  lobby: "room.riddle.soonLobby",
  round: "room.riddle.soonRound",
  kalimat: "room.riddle.afterKalimat",
} as const

export interface SamarRiddleProps {
  roomId: string
  /** Whose riddles: the lobby (`LOBBY_RIDDLE_SCOPE`) or one Quiz game (`gameRiddleScope`). */
  scope: string
  /** The wait it is shown for: the lobby's one wait, or the question The Quiz's results are about. */
  waitKey: string
  /**
   * When the answer comes: "lobby" (on a tap, or after the game), "round" (on a tap, or after
   * the next question), "kalimat" (after the game only: the word could be one of Kalimat's).
   */
  note: keyof typeof NOTE_KEY
  /** Ask a riddle. False after The Quiz's last question: only the one before is answered. */
  ask?: boolean
  className?: string
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
}

function curve(points: readonly number[]) {
  return `cubic-bezier(${points.join(", ")})`
}

function fadeIn(el: HTMLElement | null, id: string): Animation[] {
  if (!el || typeof el.animate !== "function") return []
  return [el.animate([{ opacity: 0 }, { opacity: 1 }], { id, duration: dur.state * 1000, easing: curve(ease.out) })]
}

/**
 * Whether the text runs onto more than one line, from its line boxes (the range's rects: one
 * per line for a single text node). A layout read, once, as a new line is about to be written.
 */
function wraps(textEl: HTMLElement): boolean {
  if (typeof document.createRange !== "function") return false
  const range = document.createRange()
  range.selectNodeContents(textEl)
  const rects = Array.from(range.getClientRects?.() ?? [])
  if (rects.length < 2) return false
  const first = rects[0]
  const last = rects[rects.length - 1]
  return last.top - first.top > first.height / 2
}

/**
 * The line written in, on the compositor: the text sits still while a window that clips it
 * slides open from the reading start (the window and the text move by the same distance in
 * opposite directions, two transforms in step). A fade instead: under reduced motion, for a
 * line holding a name of Allah or of the Prophet ﷺ (never swept across), and for a line that
 * wraps (the one window would uncover all its lines at once: a wipe, not a pen; at a phone's
 * width most rungs do).
 */
function writeLine(windowEl: HTMLElement, textEl: HTMLElement, text: string): Animation[] {
  if (typeof windowEl.animate !== "function") return []
  if (prefersReducedMotion() || holdsSacredName(text) || wraps(textEl)) return fadeIn(textEl, RIDDLE_INK_ID)
  const rtl = windowEl.closest("[dir='rtl'], [dir='ltr']")?.getAttribute("dir") === "rtl"
  const timing = { id: RIDDLE_INK_ID, duration: inkDuration(text, "line") * 1000, easing: curve(ease.ink) }
  return [
    windowEl.animate([{ transform: rtl ? "translateX(100%)" : "translateX(-100%)" }, { transform: "translateX(0)" }], timing),
    textEl.animate(
      [{ transform: rtl ? `translateX(calc(-100% - ${FEATHER_EM}em))` : `translateX(calc(100% + ${FEATHER_EM}em))` }, { transform: "translateX(0)" }],
      timing,
    ),
  ]
}

/**
 * Samar riddles (السَّمَر): while the table waits — the lobby, waiting for its quorum or its
 * host, and The Quiz between two questions — each member is asked the vaguest rung of a
 * Kalimat word: "While you wait: who is it? A great patriarch". Existing content only: the
 * rung and its answer are the word's own (`GET /rooms/{id}/riddle`, which never draws
 * today's word of the day nor an answer of the room's running quiz).
 *
 * - The answer is offered on a tap 30 s after the riddle was first shown, or comes "when the
 *   game starts": the page leaves at that moment, so the riddle still unanswered is read at
 *   the room's next wait, as "The last riddle, “…”, was Ibrahim." (`samar-riddle.ts`). In a
 *   lobby whose game is Kalimat the tap is not offered: the word could come up in the game.
 * - One request when the panel shows, none on a remount or a reload (the tab keeps the
 *   riddle), one per "Another riddle". Nothing is asked while the panel is not shown.
 * - Motion: the line is written in (`inkDuration(…, "line")`, `ease.ink`) only when it
 *   CHANGES (another riddle), never for the first one a panel shows, a refetch or a push.
 *   The answer and the offer fade in when they arrive under the player's eyes. Reduced
 *   motion: fades. A name of Allah or of the Prophet ﷺ is never swept across, and a line that
 *   wraps is not swept either (one window would uncover its lines at once): they fade.
 * - A refusal (a game under way, the rate limit) shows nothing: it is a pastime, not an error.
 */
export function SamarRiddle({ roomId, scope, waitKey, note, ask = true, className }: SamarRiddleProps) {
  const { t, i18n } = useTranslation()
  const lang = currentLanguage(i18n.language)

  const [record, setRecord] = useState<RiddleRecord>(() => settleRiddleRecord(readRiddleRecord(roomId, scope), waitKey, lang))
  // A new wait (or language) under the same panel: settle the record again, during render.
  const settleKey = `${waitKey}|${lang}`
  const [settledFor, setSettledFor] = useState(settleKey)
  if (settledFor !== settleKey) {
    setSettledFor(settleKey)
    setRecord((r) => settleRiddleRecord(r, waitKey, lang))
  }
  useEffect(() => writeRiddleRecord(roomId, scope, record), [roomId, scope, record])

  const { current, last } = record
  const currentId = current?.riddle.id ?? null

  // Asked when the panel has nothing to show, and once per "Another riddle".
  const [nonce, setNonce] = useState(0)
  const [asking, setAsking] = useState(false)
  const needsRiddle = ask && !current
  const queryKey = useMemo(
    () => [...getRoomRiddleApiV1RoomsRoomIdRiddleGetQueryKey({ room_id: roomId }, { lang }), { scope, waitKey, nonce }] as QueryKey,
    [roomId, lang, scope, waitKey, nonce],
  )
  const query = useGetRoomRiddleApiV1RoomsRoomIdRiddleGet<RoomRiddle, RoomRiddle, QueryKey>(
    { room_id: roomId },
    { lang },
    {
      query: {
        queryKey,
        enabled: needsRiddle || asking,
        staleTime: Infinity,
        gcTime: 0,
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    },
  )
  const fetched = query.data
  const failed = query.isError
  useEffect(() => {
    if (!fetched || (!needsRiddle && !asking)) return
    setRecord((r) => ({
      current: { riddle: fetched, lang, waitKey, shownAt: Date.now(), revealed: false },
      // asking for another: the player has moved on from the last riddle
      last: asking ? null : r.last,
    }))
    setAsking(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- adopt each answer once: the flags it reads are what it changes
  }, [fetched])
  useEffect(() => {
    if (failed && asking) setAsking(false)
  }, [failed, asking])

  // The answer is offered 30 s after the riddle was first shown (in this tab).
  const [openedAt] = useState(() => Date.now())
  const [dueLive, setDueLive] = useState<string | null>(null)
  const shownAt = current?.shownAt ?? null
  const revealed = !!current?.revealed
  const dueAtOpen = shownAt !== null && shownAt + RIDDLE_REVEAL_AFTER_MS <= openedAt
  const isDue = !!currentId && (dueAtOpen || dueLive === currentId)
  useEffect(() => {
    if (!currentId || shownAt === null || revealed || dueAtOpen) return
    const timer = setTimeout(() => setDueLive(currentId), Math.max(0, shownAt + RIDDLE_REVEAL_AFTER_MS - Date.now()))
    return () => clearTimeout(timer)
  }, [currentId, shownAt, revealed, dueAtOpen])

  // The line is written only when it changes: the riddle a panel opens on is simply there.
  const lineRef = useRef<HTMLParagraphElement>(null)
  const windowRef = useRef<HTMLSpanElement>(null)
  const textRef = useRef<HTMLSpanElement>(null)
  const shownIdRef = useRef<string | null>(currentId)
  const focusLineRef = useRef(false)
  const hint = current?.riddle.hint ?? ""
  useLayoutEffect(() => {
    const previous = shownIdRef.current
    shownIdRef.current = currentId
    if (!currentId || previous === null || previous === currentId) return
    if (focusLineRef.current) {
      focusLineRef.current = false
      lineRef.current?.focus({ preventScroll: true })
    }
    const windowEl = windowRef.current
    const textEl = textRef.current
    if (!windowEl || !textEl) return
    const running = writeLine(windowEl, textEl, hint)
    return () => running.forEach((animation) => animation.cancel())
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the hint belongs to the riddle: a new id is a new line
  }, [currentId])

  // The answer fades in when the player asks for it, and takes focus (the button is gone).
  const answerRef = useRef<HTMLParagraphElement>(null)
  const [revealedNow, setRevealedNow] = useState<string | null>(null)
  useLayoutEffect(() => {
    if (!revealedNow || revealedNow !== currentId) return
    answerRef.current?.focus({ preventScroll: true })
    const running = fadeIn(answerRef.current, RIDDLE_FADE_ID)
    return () => running.forEach((animation) => animation.cancel())
  }, [revealedNow, currentId])

  // The offer fades in when it comes under the player's eyes (not when it was due already).
  const offerRef = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    if (!dueLive || dueLive !== currentId) return
    const running = fadeIn(offerRef.current, RIDDLE_FADE_ID)
    return () => running.forEach((animation) => animation.cancel())
  }, [dueLive, currentId])

  const reveal = () => {
    if (!currentId) return
    setRevealedNow(currentId)
    setRecord((r) => (r.current ? { ...r, current: { ...r.current, revealed: true } } : r))
  }
  const another = () => {
    if (asking) return
    focusLineRef.current = true
    setNonce((n) => n + 1)
    setAsking(true)
  }

  const loading = needsRiddle && !failed && !fetched
  if (!current && !last && !loading) return null

  const answerText = (riddle: RoomRiddle) => riddle.answer.word_display
  const arabic = current ? (current.riddle.answer.word_ar_vocalized ?? current.riddle.answer.word_ar) : null
  const showArabic = !!arabic && arabic !== current?.riddle.answer.word_display

  return (
    <section aria-label={t("room.riddle.label")} className={cn("grid gap-3 text-[13.5px] leading-normal text-muted-foreground", className)}>
      {last ? (
        <p className="text-pretty [&_b]:font-medium [&_b]:text-foreground">
          <Trans i18nKey="room.riddle.last" values={{ hint: last.riddle.hint, answer: answerText(last.riddle) }} components={{ b: <b dir="auto" /> }} />
        </p>
      ) : null}

      {current ? (
        <div className="grid gap-1">
          <p>{t(riddleAskKey(current.riddle.category))}</p>
          {/* The rung, in Amiri. A clipping box, a window that clips (and runs FEATHER_EM past
              the line, its soft edge clipped by the box at rest), the text: at rest nothing
              moves and the whole line is there. */}
          <p ref={lineRef} tabIndex={-1} className="type-nass text-[19px] leading-[1.5] text-foreground outline-none">
            <span className="block overflow-hidden">
              <span
                ref={windowRef}
                className="block -me-[1.25em] overflow-hidden pe-[1.25em] [mask-image:linear-gradient(to_right,#000_calc(100%_-_1.25em),transparent)] rtl:[mask-image:linear-gradient(to_left,#000_calc(100%_-_1.25em),transparent)]"
              >
                <span ref={textRef} className="block py-[0.1em] text-pretty">
                  {current.riddle.hint}
                </span>
              </span>
            </span>
          </p>

          {current.revealed ? (
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <p ref={answerRef} tabIndex={-1} className="outline-none [&_b]:font-medium [&_b]:text-foreground">
                <Trans i18nKey="room.riddle.was" values={{ answer: answerText(current.riddle) }} components={{ b: <b dir="auto" /> }} />
                {showArabic ? (
                  <>
                    {" · "}
                    <span lang="ar" dir="rtl" className="bidi-isolate font-nass text-[17px] text-foreground">
                      {arabic}
                    </span>
                  </>
                ) : null}
              </p>
              {ask ? (
                <Button variant="link" size="sm" onClick={another} loading={asking}>
                  {t("room.riddle.another")}
                </Button>
              ) : null}
            </div>
          ) : (
            <p className="text-pretty">
              {t(NOTE_KEY[note])}
              {isDue && note !== "kalimat" ? (
                <>
                  {" "}
                  <span ref={offerRef} className="inline-block">
                    <Button variant="link" size="sm" onClick={reveal}>
                      {t("room.riddle.show")}
                    </Button>
                  </span>
                </>
              ) : null}
            </p>
          )}
        </div>
      ) : loading ? (
        // bare warp where the question and the rung will be: the panel does not jump when it lands
        <div className="grid gap-1.5" aria-hidden="true">
          <Skeleton className="h-4 w-44" />
          <Skeleton className="h-7 w-full max-w-[320px]" />
        </div>
      ) : null}
    </section>
  )
}
