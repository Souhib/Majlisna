import { type CSSProperties, type RefObject, useLayoutEffect, useRef } from "react"
import { dur, ease } from "@/lib/motion"
import { cn } from "@/lib/utils"

/** sessionStorage: the home's name has been woven in this tab (DESIGN.md §7, the kashida woven once). */
export const KASHIDA_WOVEN_KEY = "majlisna-kashida-woven"
/** The weave waits this long at most for the wordmark's face: never holds the band out longer. */
export const KASHIDA_FONT_WAIT_MS = 3000

/**
 * The band, full length in the kashida's clipping box, comes in from the right: Arabic's reading
 * start. Held 2 px past the clip's end, not at exactly 100%: the clip's width is fractional, and
 * at 100% the band's leading edge showed as a 1-device-pixel madder line in the open joint for as
 * long as the face took to load. The end is the band's rest, so the woven state is unchanged.
 */
const WEAVE_KEYFRAMES: Keyframe[] = [{ transform: "translateX(calc(100% + 2px))" }, { transform: "translateX(0)" }]
const WEAVE_TIMING: KeyframeAnimationOptions = { duration: dur.ceremony * 1000, easing: `cubic-bezier(${ease.ink.join(", ")})` }

/**
 * Whether this mount weaves: once per session (the flag is taken here, at the first commit),
 * never under reduced motion, never without Web Animations, and never when the session
 * cannot be remembered (a reload could not be told from a first visit).
 */
function claimKashidaWeave(band: HTMLElement): boolean {
  if (typeof band.animate !== "function") return false
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return false
  try {
    if (sessionStorage.getItem(KASHIDA_WOVEN_KEY)) return false
    sessionStorage.setItem(KASHIDA_WOVEN_KEY, "1")
    return true
  } catch {
    return false
  }
}

/** The wordmark's own face, loaded (asked for explicitly: at the first commit no glyph has asked yet), then every pending face. */
function wordmarkFaceReady(el: Element): Promise<unknown> {
  const fonts = document.fonts
  if (!fonts) return Promise.resolve()
  const style = getComputedStyle(el)
  return fonts.load(`${style.fontWeight} ${style.fontSize} ${style.fontFamily}`, "مجلسنا").then(() => fonts.ready)
}

/**
 * The kashida woven once: from the first frame the band is held out of its box by its own
 * paused animation (the letters are drawn, the joint is open); after the face is ready, the
 * next frame plays it. A cancelled or missing animation leaves the band where it rests.
 */
function useKashidaWeave(bandRef: RefObject<HTMLElement | null>, enabled: boolean) {
  // null: not asked yet; kept across StrictMode's effect re-run, so the claim is not lost
  const claimed = useRef<boolean | null>(null)
  useLayoutEffect(() => {
    const band = bandRef.current
    if (!enabled || !band) return
    if (claimed.current === null) claimed.current = claimKashidaWeave(band)
    if (!claimed.current) return

    const anim = band.animate(WEAVE_KEYFRAMES, WEAVE_TIMING)
    anim.pause()
    let played = false
    let frame = 0
    const play = () => {
      if (played) return
      played = true
      clearTimeout(fallback)
      frame = requestAnimationFrame(() => anim.play())
    }
    const fallback = setTimeout(play, KASHIDA_FONT_WAIT_MS)
    wordmarkFaceReady(band).then(play, play)
    return () => {
      // once it has played (or the page left), this mount never weaves again
      if (played) claimed.current = false
      played = true
      clearTimeout(fallback)
      cancelAnimationFrame(frame)
      anim.cancel()
    }
  }, [bandRef, enabled])
}

/**
 * Wordmark: مجلسنا as LIVE TEXT in Reem Kufi 700, its lam–seen joint stretched into
 * al-madd, the woven kashida (sketch: `.madd`). Two halves that each end or start with
 * a tatweel, and a band between them overlapping both tatweel ends, all inside its own
 * dir="rtl" so it shapes correctly on an English page.
 *
 * - size >= 80 px: the kashida is woven (madd band, selvedge in the letters' colour,
 *   night or day by theme).
 * - size < 80 px: the kashida is ink with one 1.5 px madder thread at its centre.
 * Override with `woven`.
 *
 * Colour is `currentColor` (set `className="text-lockup"` for the nav's brass/ink).
 * The Arabic is hidden from assistive tech and replaced by `label` (default "مجلسنا");
 * pass `label={null}` when a neighbour already names it (the Lockup does).
 *
 * Frozen outlines for favicons and OG cards: src/assets/brand/wordmark-*.svg.
 *
 * <Wordmark size={32} />                  // nav
 * <Wordmark size={200} stretch={2.25} />  // the giant name on the horizon
 */
export interface WordmarkProps {
  /**
   * Font size: px as a number (default 32, the nav lockup), or any CSS length for a
   * fluid name, e.g. "clamp(80px, 19vw, 236px)" on the horizon (a string counts as
   * large: woven, stretch 2.25 em, unless you say otherwise). Size it so it never
   * overflows a 390 px phone.
   */
  size?: number | string
  /**
   * Length of the stretched kashida: a number in em (default 0.95 below 80 px, 2.25
   * above), or any CSS length, e.g. "var(--hero-stretch)" when a stylesheet changes it
   * per breakpoint (the home hero: 2.25 em on desktop, 1.45 em on phones).
   */
  stretch?: number | string
  /** Force the woven (true) or ink (false) kashida. */
  woven?: boolean
  /**
   * Weave the band once per session (the home's name on the horizon, DESIGN.md §7): after
   * the fonts are ready, the band comes in from the right through the kashida's own clip,
   * 1100 ms on --ease-ink. The letters never move; reduced motion moves nothing. Woven
   * kashidas only.
   */
  weave?: boolean
  /** Accessible name; null when a neighbouring label already names the brand. */
  label?: string | null
  className?: string
  style?: CSSProperties
}

export function Wordmark({ size = 32, stretch, woven, weave = false, label = "مجلسنا", className, style }: WordmarkProps) {
  const large = typeof size === "string" || size >= 80
  const isWoven = woven ?? large
  const k = stretch ?? (large ? 2.25 : 0.95)
  const kashida = typeof k === "number" ? `${k}em` : k
  const bandRef = useRef<HTMLElement>(null)
  useKashidaWeave(bandRef, weave && isWoven)
  return (
    <span
      className={cn("madd", className)}
      lang="ar"
      dir="rtl"
      style={{ fontSize: size, ...style }}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      <span aria-hidden="true">مجلـ</span>
      <i aria-hidden="true" className={cn("k", !isWoven && "k-ink")} style={{ "--stretch": kashida } as CSSProperties}>
        {/* the woven band, full length in the kashida's clip (styles/brand.css) */}
        {isWoven ? <i ref={bandRef} className="k-band" /> : null}
      </i>
      <span aria-hidden="true">ـسنا</span>
    </span>
  )
}

/**
 * Lockup: the wordmark, a 1 px brass rule, then MAJLISNA in spaced Marcellus capitals
 * (Qandil's lockup). The Arabic stays at the reading start in both directions. Colour
 * is the --lockup token (brass at night, ink by day). The Latin part hides on phones
 * when `compactOnMobile` is set.
 *
 * <Link to="/" aria-label={t("nav.home")}><Lockup /></Link>
 */
export interface LockupProps {
  /**
   * Wordmark size: px as a number (default 32), or a CSS length such as
   * "var(--lockup-size)" when a stylesheet sizes it per breakpoint (the nav: 30 px on
   * phones, 38 px above 2200 px). The lockup's kashida is always ink with the madder
   * thread, whatever the size.
   */
  size?: number | string
  /** Hide the Latin "Majlisna" below 760 px. */
  compactOnMobile?: boolean
  className?: string
}

export function Lockup({ size = 32, compactOnMobile = false, className }: LockupProps) {
  return (
    <span className={cn("inline-flex flex-none items-center gap-3.5 text-lockup", className)}>
      <Wordmark size={size} woven={false} stretch={0.95} label={null} style={{ paddingBlockStart: 4 }} />
      <span
        lang="en"
        className={cn(
          "flex h-[18px] items-center border-s border-line-brass-strong ps-3.5 font-display text-[12.5px] uppercase leading-none tracking-[0.26em]",
          compactOnMobile && "max-[760px]:hidden",
        )}
      >
        Majlisna
      </span>
    </span>
  )
}
