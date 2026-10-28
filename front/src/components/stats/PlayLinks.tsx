import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Panel, PanelHeader } from "@/components/ui/panel"

/**
 * "Your play": the doors from a player's own pages to the rest of their space, as one
 * plain hairline list of text links: each row its title and what is behind it. No icon
 * column and no chevrons (that read as a settings menu).
 */
const LINKS = [
  { to: "/stats", title: "stats.title", body: "profile.viewStats" },
  { to: "/achievements", title: "achievements.title", body: "profile.viewAchievements" },
  { to: "/challenges", title: "challenges.title", body: "profile.viewChallenges" },
  { to: "/notebook", title: "notebook.title", body: "profile.viewNotebook" },
  { to: "/friends", title: "friends.title", body: "profile.viewFriends" },
  { to: "/rooms", title: "nav.rooms", body: "profile.joinOrCreate" },
] as const

export function PlayLinks() {
  const { t } = useTranslation()
  return (
    <Panel flush aria-labelledby="play-links-title">
      <PanelHeader className="mb-0 px-4 pb-3 pt-4 sm:px-[22px] sm:pt-[22px]" title={<span id="play-links-title">{t("profile.yourPlay")}</span>} />
      <ul>
        {LINKS.map(({ to, title, body }) => (
          <li key={to} className="border-t border-line">
            <Link to={to} className="group grid gap-0.5 px-4 py-3.5 focus-visible:-outline-offset-2 sm:px-[22px]">
              <span className="font-medium underline decoration-line-brass decoration-1 underline-offset-4 transition-colors duration-(--dur-state) group-hover:decoration-brass">
                {t(title)}
              </span>
              <span className="text-[14px] text-muted-foreground">{t(body)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
