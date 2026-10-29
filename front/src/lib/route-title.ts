import type { TFunction } from "i18next"

/**
 * The fallback document title for a path (lib/document-title): the page's own name as
 * its heading says it, in the page's language. Pages whose name comes from their data
 * (the lobby, a player) refine it with `useDocumentTitle`.
 */
const TITLE_KEYS: [RegExp, string][] = [
  [/^\/rooms\/create\/?$/, "room.createPage.title"],
  [/^\/rooms(\/.*)?$/, "nav.rooms"],
  [/^\/game\/undercover\//, "games.undercover.name"],
  [/^\/game\/codenames\//, "games.codenames.name"],
  [/^\/game\/wordquiz\//, "games.wordQuiz.name"],
  [/^\/game\/mcqquiz\//, "games.mcqQuiz.name"],
  [/^\/notebook\/?$/, "notebook.title"],
  [/^\/today\/?$/, "daily.name"],
  [/^\/profile\/?$/, "nav.profile"],
  [/^\/stats\/?$/, "stats.title"],
  [/^\/achievements\/?$/, "achievements.title"],
  [/^\/challenges\/?$/, "challenges.title"],
  [/^\/friends\/?$/, "friends.title"],
  [/^\/leaderboard\/?$/, "nav.leaderboard"],
  [/^\/about\/?$/, "nav.about"],
  [/^\/credits\/?$/, "credits.title"],
  [/^\/privacy\/?$/, "privacy.title"],
  [/^\/auth\/login\/?$/, "nav.login"],
  [/^\/auth\/register\/?$/, "nav.register"],
  [/^\/auth\/forgot-password\/?$/, "auth.forgotPassword"],
  [/^\/auth\/reset-password\/?$/, "auth.resetPassword"],
  [/^\/auth\/verify-email\/?$/, "auth.verifyingEmail"],
]

export function titleForPath(pathname: string, t: TFunction): string {
  const match = TITLE_KEYS.find(([pattern]) => pattern.test(pathname))
  const name = match ? t(match[1], { defaultValue: "" }) : ""
  return name ? t("meta.pageTitle", { title: name }) : t("meta.defaultTitle")
}
