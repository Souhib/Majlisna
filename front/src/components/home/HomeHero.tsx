import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Wordmark } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"
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

/** The sky of one light (also rendered on its own by the sky's contract test). */
export function HomeSky({ name }: { name: string }) {
  const base = `/sky/${name}`
  return (
    <div className="home-sky" aria-hidden="true">
      <picture>
        <source media="(max-width: 760px)" srcSet={`${base}.800.webp 800w, ${base}.1000.webp 1000w`} sizes="100vw" width={1000} height={800} />
        <source
          media="(max-width: 1100px)"
          srcSet={`${base}.tab800.webp 800w, ${base}.tab1200.webp 1200w, ${base}.tab1600.webp 1600w`}
          sizes={TABLET_SKY_SIZES}
          width={1600}
          height={800}
        />
        <img
          src={`${base}.1600.webp`}
          srcSet={`${base}.1600.webp 1600w, ${base}.2400.webp 2400w`}
          sizes="100vw"
          width={1600}
          height={427}
          alt=""
          fetchPriority="high"
          decoding="async"
        />
      </picture>
    </div>
  )
}

export function HomeHero() {
  const { t } = useTranslation()
  const light = useResolvedTheme()
  const night = light === "dark"

  return (
    <section className="home-hero" aria-labelledby="home-title">
      {/* keyed by the light so the browser never shows the other sky while swapping */}
      <HomeSky key={light} name={SKY[light]} />
      <div className="home-ground" aria-hidden="true" />

      <div className="home-word home-wrap" aria-hidden="true">
        <Wordmark size="1em" stretch="var(--hero-stretch)" woven label={null} />
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
