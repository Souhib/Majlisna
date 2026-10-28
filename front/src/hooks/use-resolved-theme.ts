import { useSyncExternalStore } from "react"

export type ResolvedTheme = "light" | "dark"

/**
 * The light actually on screen ("dark" = the night, "light" = the afternoon), read from
 * `<html data-theme>`. ThemeProvider and the pre-paint script in index.html both write
 * that attribute, and the Samar tokens key on it, so this can never disagree with the
 * colours the page is drawn in (unlike `useTheme().theme`, which may say "system").
 *
 * Used where markup, not only colour, changes with the light: the home sky and its
 * title, the theme toggle's icon and label, the Register button's fill.
 */
function read(): ResolvedTheme {
  if (typeof document === "undefined") return "dark"
  return document.documentElement.dataset.theme === "light" ? "light" : "dark"
}

function subscribe(onChange: () => void) {
  if (typeof MutationObserver === "undefined") return () => {}
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] })
  return () => observer.disconnect()
}

export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, read, () => "dark")
}
