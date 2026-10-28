import { type CSSProperties } from "react"
import { cn } from "@/lib/utils"

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
  /** Accessible name; null when a neighbouring label already names the brand. */
  label?: string | null
  className?: string
  style?: CSSProperties
}

export function Wordmark({ size = 32, stretch, woven, label = "مجلسنا", className, style }: WordmarkProps) {
  const large = typeof size === "string" || size >= 80
  const isWoven = woven ?? large
  const k = stretch ?? (large ? 2.25 : 0.95)
  const kashida = typeof k === "number" ? `${k}em` : k
  return (
    <span
      className={cn("madd", className)}
      lang="ar"
      dir="rtl"
      style={{ fontSize: size, ...style }}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      <span aria-hidden="true">مجلـ</span>
      <i aria-hidden="true" className={cn("k", !isWoven && "k-ink")} style={{ "--stretch": kashida } as CSSProperties} />
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
