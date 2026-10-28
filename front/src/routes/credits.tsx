import { createFileRoute } from "@tanstack/react-router"
import { ArrowUpRight } from "lucide-react"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"
import jabreen800 from "@/assets/brand/jabreen-niches.duo.800.webp"
import { Separator } from "@/components/ui/separator"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"

export const Route = createFileRoute("/credits")({
  component: CreditsPage,
})

/**
 * Credits: the visible attribution the Creative Commons licences ask for (title, author,
 * source, licence, and what we changed), for the two photographs the design is built on.
 * Provenance in full: public/sky/SOURCES.txt and src/assets/brand/SOURCES.txt. Linked
 * from the footer on every page. Titles and names stay as their authors wrote them.
 */
interface Work {
  key: "sky" | "jabreen"
  title: string
  /** As the source credits it. */
  author: string
  source: string
  licence: { name: string; href: string }
  thumb: (light: "dark" | "light") => string
}

const WORKS: Work[] = [
  {
    key: "sky",
    title: "SHIMM Astronomical System at AlUla Manara Site in Northwestern Saudi Arabia (2025)",
    author: "Saudi Press Agency (SPA), via the Saudi Photos platform",
    source:
      "https://commons.wikimedia.org/wiki/File:SHIMM_Astronomical_System_at_AlUla_Manara_Site_in_Northwestern_Saudi_Arabia_(2025).jpg",
    licence: { name: "CC BY-SA 4.0", href: "https://creativecommons.org/licenses/by-sa/4.0/" },
    thumb: (light) => (light === "dark" ? "/sky/sky-maghrib.800.webp" : "/sky/sky-asr.800.webp"),
  },
  {
    key: "jabreen",
    title: "Jabreen Castle, Oman - 2024 13",
    author: "dconvertini (Flickr)",
    source: "https://commons.wikimedia.org/wiki/File:Jabreen_Castle,_Oman_-_2024_13.jpg",
    licence: { name: "CC BY-SA 2.0", href: "https://creativecommons.org/licenses/by-sa/2.0/" },
    thumb: () => jabreen800,
  },
]

const FONTS = ["Reem Kufi", "Marcellus", "Readex Pro", "Amiri", "Aref Ruqaa"]

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-11 items-center gap-1.5 text-brass underline decoration-line-brass-strong underline-offset-[5px] hover:decoration-brass sm:min-h-0"
    >
      {children}
      <ArrowUpRight className="size-3.5 shrink-0 rtl-flip" aria-hidden="true" />
      <span className="sr-only">{t("ui.opensInNewTab")}</span>
    </a>
  )
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 border-t border-line py-3 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-6">
      <dt className="type-label pt-0.5">{term}</dt>
      <dd className="min-w-0 text-[16px] leading-relaxed text-foreground text-pretty">{children}</dd>
    </div>
  )
}

function CreditsPage() {
  const { t } = useTranslation()
  const light = useResolvedTheme()

  return (
    <div className="page-wrap py-[clamp(48px,7vw,104px)]">
      <div className="mx-auto max-w-[62rem]">
        <header className="max-w-[46rem]">
          <h1 className="type-h2">{t("credits.title")}</h1>
          <p className="type-lede mt-5">{t("credits.lede")}</p>
        </header>

        <section className="mt-[clamp(40px,5vw,72px)]" aria-labelledby="credits-images">
          <h2 id="credits-images" className="type-title">
            {t("credits.images")}
          </h2>
          <ol className="mt-6 grid gap-[clamp(32px,4vw,56px)]">
            {WORKS.map((w) => (
              <li
                key={w.key}
                className="grid gap-5 border-t border-line-brass pt-6 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] md:gap-10"
              >
                <img
                  src={w.thumb(light)}
                  alt={t(w.key === "sky" ? (light === "dark" ? "credits.sky.altNight" : "credits.sky.altDay") : "credits.jabreen.alt")}
                  width={800}
                  height={640}
                  loading="lazy"
                  decoding="async"
                  className="aspect-[5/4] w-full max-w-[15rem] rounded-sm border border-line-brass object-cover"
                />
                <div className="min-w-0">
                  {/* the title as its author wrote it, isolated, in a heading that follows the page */}
                  <h3 className="type-panel text-pretty">
                    <bdi lang="en">“{w.title}”</bdi>
                  </h3>
                  <dl className="mt-4">
                    <Row term={t("credits.author")}>
                      <span lang="en" dir="ltr" className="bidi-isolate">
                        {w.author}
                      </span>
                    </Row>
                    <Row term={t("credits.source")}>
                      <ExternalLink href={w.source}>Wikimedia Commons</ExternalLink>
                    </Row>
                    <Row term={t("credits.licence")}>
                      <ExternalLink href={w.licence.href}>
                        <span dir="ltr" className="bidi-isolate">
                          {w.licence.name}
                        </span>
                      </ExternalLink>
                      <span className="text-muted-foreground"> · {t("credits.sameLicence")}</span>
                    </Row>
                    <Row term={t("credits.changes")}>{t(`credits.${w.key}.changes`)}</Row>
                    <Row term={t("credits.usedFor")}>{t(`credits.${w.key}.use`)}</Row>
                  </dl>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <Separator className="my-[clamp(40px,5vw,72px)]" />

        <section aria-labelledby="credits-type" className="max-w-[46rem]">
          <h2 id="credits-type" className="type-title">
            {t("credits.typefaces")}
          </h2>
          <dl className="mt-6 border-b border-line">
            <Row term={t("credits.fonts")}>
              <span lang="en" dir="ltr" className="bidi-isolate">
                {FONTS.join(", ")}
              </span>
              <span className="block text-muted-foreground">{t("credits.fontsBody")}</span>
            </Row>
            <Row term={t("credits.licence")}>
              <ExternalLink href="https://openfontlicense.org/">SIL Open Font License 1.1</ExternalLink>
            </Row>
            <Row term={t("credits.icons")}>
              <span lang="en" dir="ltr" className="bidi-isolate">
                Lucide
              </span>
              <span className="text-muted-foreground"> · </span>
              <ExternalLink href="https://lucide.dev/license">ISC</ExternalLink>
            </Row>
          </dl>
        </section>
      </div>
    </div>
  )
}
