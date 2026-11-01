import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { useEffect, useRef } from "react"
import { Trans, useTranslation } from "react-i18next"
import { Wordmark } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"
import { SKY_PRELOAD_LEAD_MS, type SkyTurn } from "@/lib/sky-light"
import { useSkyTurn } from "@/providers/ThemeProvider"
import { HalqaCard } from "./HalqaCard"
import { focusHeroJoin, HeroJoinForm } from "./HeroJoinForm"

/**
 * The home's first screen (sketch A dark, E light, F/G Arabic): one horizon under two
 * lights. The sky is ONE pre-composed picture per light (public/sky/), art-directed for
 * phones (≤ 760 px), tablets (761–1100 px: an 800, 1200 or 1600 wide 2:1 crop) and
 * desktops, always `object-fit: cover`
 * with its bottom edge on the horizon, so the mesas run edge to edge at every width.
 * index.html preloads the file the current light and width will use.
 *
 * The title changes with the sky: "The night is for riddles." at night, "Come in, the
 * majlis is open." in the afternoon.
 */
const SKY = { dark: "sky-maghrib", light: "sky-asr" } as const

/**
 * How wide the tablet crop (2:1) is drawn. The sky box is the full width and 47 % of
 * `--hh` = clamp(720px, 100svh, 1440px) high (home.css), and `object-fit: cover` fills
 * it: by its width when the viewport is at least 0.94 as wide as it is high, otherwise
 * by its height, 2 × 0.47 × 100vh wide (a 768 × 1024 iPad draws it 962 px wide, not
 * 768). Telling the browser so picks tab1200 there at DPR 1, never a stretched tab800.
 * index.html's preload repeats this value: change both (front/CLAUDE.md).
 */
const TABLET_SKY_SIZES = "(min-aspect-ratio: 47/50) 100vw, 94vh"

/**
 * The sky's three ranges, in the picture's order: the phone and tablet sources, then the
 * desktop image (no media query: what the sources leave). One source of truth for the
 * <picture> and for `warmSky`; index.html's preload repeats them (front/CLAUDE.md).
 */
function skyRanges(name: string) {
  const base = `/sky/${name}`
  return {
    phone: { media: "(max-width: 760px)", srcSet: `${base}.800.webp 800w, ${base}.1000.webp 1000w`, sizes: "100vw" },
    tablet: {
      media: "(max-width: 1100px)",
      srcSet: `${base}.tab800.webp 800w, ${base}.tab1200.webp 1200w, ${base}.tab1600.webp 1600w`,
      sizes: TABLET_SKY_SIZES,
    },
    desktop: { src: `${base}.1600.webp`, srcSet: `${base}.1600.webp 1600w, ${base}.2400.webp 2400w`, sizes: "100vw" },
  }
}

/** The sky of one light (also rendered on its own by the sky's contract test). */
export function HomeSky({ name }: { name: string }) {
  const { phone, tablet, desktop } = skyRanges(name)
  return (
    <div className="home-sky" aria-hidden="true">
      <picture>
        <source media={phone.media} srcSet={phone.srcSet} sizes={phone.sizes} width={1000} height={800} />
        <source media={tablet.media} srcSet={tablet.srcSet} sizes={tablet.sizes} width={1600} height={800} />
        <img src={desktop.src} srcSet={desktop.srcSet} sizes={desktop.sizes} width={1600} height={427} alt="" fetchPriority="high" decoding="async" />
      </picture>
    </div>
  )
}

/**
 * Fetch, quietly, the very file the picture will draw for `name` at this width (the same
 * range, candidates and sizes): when the sky turns, the new picture finds it in the cache
 * and the crossfade lands on a sky, not on its fallback colour.
 */
export function warmSky(name: string): HTMLImageElement {
  const { phone, tablet, desktop } = skyRanges(name)
  const range = [phone, tablet].find((r) => window.matchMedia(r.media).matches) ?? desktop
  const img = new Image()
  img.decoding = "async"
  img.fetchPriority = "low"
  img.sizes = range.sizes
  img.srcset = range.srcSet
  return img
}

/**
 * "Follow the sky" turns the home's sky at Maghrib and at sunrise (ThemeProvider): fetch
 * the other sky SKY_PRELOAD_LEAD_MS (10 min) before, never at load (the load's one /sky/
 * request is the current light's, preloaded by index.html), and only on this page.
 */
export function useSkyWarmUp(turn: SkyTurn | null) {
  const at = turn?.at ?? null
  const light = turn?.light ?? null
  // the image fetched ahead, held until the turn draws it (an image nobody holds may be dropped)
  const warmed = useRef<HTMLImageElement | null>(null)
  useEffect(() => {
    if (at === null || light === null) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const arm = () => {
      timer = setTimeout(
        () => {
          warmed.current = warmSky(SKY[light])
        },
        Math.max(0, at - SKY_PRELOAD_LEAD_MS - Date.now()),
      )
    }
    if (document.readyState === "complete") arm()
    else window.addEventListener("load", arm, { once: true })
    return () => {
      clearTimeout(timer)
      window.removeEventListener("load", arm)
    }
  }, [at, light])
}

export function HomeHero() {
  const { t } = useTranslation()
  const light = useResolvedTheme()
  const night = light === "dark"
  useSkyWarmUp(useSkyTurn())

  return (
    <section className="home-hero" aria-labelledby="home-title">
      {/* keyed by the light so the browser never shows the other sky while swapping */}
      <HomeSky key={light} name={SKY[light]} />
      <div className="home-ground" aria-hidden="true" />

      <div className="home-word home-wrap" aria-hidden="true">
        <Wordmark size="1em" stretch="var(--hero-stretch)" woven weave label={null} />
      </div>

      <div className="home-hero-body home-wrap">
        <div>
          <h1 id="home-title">{night ? t("home.hero.titleNight") : t("home.hero.titleDay")}</h1>
          <p className="home-lede">
            <Trans i18nKey={night ? "home.hero.ledeNight" : "home.hero.ledeDay"} components={{ em: <em /> }} />
          </p>
          <div className="home-actions">
            <Button
              asChild
              className="min-[2200px]:h-14 min-[2200px]:px-[26px] min-[2200px]:text-[17px]"
              iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
            >
              <Link to="/rooms/create">{t("home.hero.openRoom")}</Link>
            </Button>
            <HeroJoinForm />
          </div>
        </div>
        <HalqaCard onTakeSeat={focusHeroJoin} />
      </div>
    </section>
  )
}
