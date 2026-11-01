import { useSyncExternalStore } from "react"

export type ResolvedTheme = "light" | "dark"

/**
 * The light actually on screen ("dark" = the night, "light" = the afternoon), read from
 * `<html data-theme>`. ThemeProvider and the pre-paint script in index.html both write
 * that attribute, and the Samar tokens key on it, so this can never disagree with the
 * colours the page is drawn in (unlike `useTheme().theme`, which may say "system" or
 * "sky").
 *
 * Used where markup, not only colour, changes with the light: the home sky and its
 * title, the theme toggle's icon and label, the Register button's fill.
 */
function read(): ResolvedTheme {
  if (typeof document === "undefined") return "dark"
  return document.documentElement.dataset.theme === "light" ? "light" : "dark"
}

const listeners = new Set<() => void>()

/**
 * Tell every reader the light changed, in this very task. ThemeProvider calls it right
 * after writing `data-theme`: the sky's turn writes it inside a view transition's
 * `flushSync`, and the browser captures the new state as soon as that update returns, so
 * the title and the sky must already be the new ones (the MutationObserver below answers a
 * microtask later; it stays for any other writer of the attribute).
 */
export function announceResolvedTheme() {
  for (const listener of listeners) listener()
}

function subscribe(onChange: () => void) {
  listeners.add(onChange)
  const observer = typeof MutationObserver === "undefined" ? null : new MutationObserver(onChange)
  observer?.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] })
  return () => {
    listeners.delete(onChange)
    observer?.disconnect()
  }
}

export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, read, () => "dark")
}
