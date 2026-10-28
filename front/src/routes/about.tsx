import { createFileRoute, Link } from "@tanstack/react-router"
import { Trans } from "react-i18next"
import { AboutIntro } from "@/components/about/AboutIntro"
import { GameRules } from "@/components/about/GameRules"
import { MakerSection } from "@/components/about/MakerSection"
import { READ_RAILS } from "@/components/about/rails"
import { SupportCharities } from "@/components/about/SupportCharities"
import { Separator } from "@/components/ui/separator"

export const Route = createFileRoute("/about")({
  component: AboutPage,
})

/**
 * About, in Read mode: what Majlisna is (the samar, four games, three languages), how
 * the games play (the targets of the home's "How it plays" links: #undercover,
 * #codenames, #kalimat, #quiz), the two charities, who made it (#maker), and where the
 * credits live. Everything is on the page from the first frame: the old scroll-in
 * reveals left whole sections at opacity 0 until they were scrolled to.
 */
const SECTION_GAP = "my-[clamp(48px,6vw,88px)]"

function AboutPage() {
  return (
    <div className="page-wrap py-[clamp(48px,7vw,104px)]">
      <div className="mx-auto max-w-[62rem]">
        <AboutIntro />
        <Separator className={SECTION_GAP} />
        <GameRules />
        <Separator className={SECTION_GAP} />
        <SupportCharities />
        <Separator className={SECTION_GAP} />
        <MakerSection />
        <Separator variant="line" className={SECTION_GAP} />
        <div className={READ_RAILS}>
          <p className="text-[15.5px] leading-relaxed text-pretty text-muted-foreground md:col-start-2">
            <Trans
              i18nKey="about.creditsLine"
              // not <link>: that is a void element in HTML, and the parser would drop its text
              components={{
                page: (
                  <Link to="/credits" className="font-medium text-brass underline decoration-line-brass-strong underline-offset-[5px] hover:decoration-brass" />
                ),
              }}
            />
          </p>
        </div>
      </div>
    </div>
  )
}
