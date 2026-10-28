/**
 * The document title (WCAG 2.4.2 Page Titled), in the page's language: "Kunnash ·
 * Majlisna", "Yusuf’s majlis · Majlisna". Every page used to keep index.html's English
 * "Majlisna · Islamic party games", so a screen reader, the tab strip and the history
 * could not tell a game from the notebook or the 404.
 *
 * Two layers: the shell sets a FALLBACK from the route (root layout, `titleForPath`), and
 * a page that knows better from its data (the lobby's host, a player's name, the 404)
 * pushes an OVERRIDE with `useDocumentTitle`. Children's effects run before their
 * parent's, so a single "last writer wins" would let the shell overwrite the page: the
 * override always wins over the fallback instead.
 */
let fallback = ""
const overrides: { id: number; title: string }[] = []
let nextId = 1

function apply() {
  const title = overrides.length ? overrides[overrides.length - 1].title : fallback
  if (title && typeof document !== "undefined") document.title = title
}

export function setFallbackTitle(title: string): void {
  fallback = title
  apply()
}

/** Push a page's own title; returns the function that removes it. */
export function pushTitle(title: string): () => void {
  const entry = { id: nextId++, title }
  overrides.push(entry)
  apply()
  return () => {
    const i = overrides.findIndex((o) => o.id === entry.id)
    if (i >= 0) overrides.splice(i, 1)
    apply()
  }
}

/** For tests. */
export function resetDocumentTitle(): void {
  fallback = ""
  overrides.length = 0
}
