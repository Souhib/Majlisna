import { type RefObject, useEffect, useRef } from "react"

/**
 * The element a phase change sends focus to, as a CSS selector inside the game region,
 * by phase. A phase not named falls back to `"h2"`: each game phase's title.
 */
export type PhaseFocusTargets = Partial<Record<string, string>>

export interface PhaseFocusOptions {
  /** Per phase (its key, as passed to the hook), the selector of its title. */
  targets?: PhaseFocusTargets
  /** The selector for a phase `targets` does not name. Default `"h2"`. */
  fallback?: string
}

const DEFAULT_TARGET = "h2"

/** Inputs that are a place to type (a radio or a checkbox is not). */
const NON_TEXT_INPUTS = new Set(["button", "checkbox", "radio", "range", "reset", "submit", "color", "file", "image"])

/** True when the element takes typing: a text field, a textarea, a select, an editable region. */
function takesTyping(element: Element): boolean {
  if (element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) return true
  if (element instanceof HTMLInputElement) return !NON_TEXT_INPUTS.has(element.type)
  return element instanceof HTMLElement && element.isContentEditable
}

/**
 * True when focus may be moved without taking it from anyone: it is on nothing (`<body>`,
 * where it falls when the element that held it is unmounted by the phase swap), or on
 * something inside the game that is not a field being typed in. Focus in the chat, the
 * nav, a dialog or the prayer veil (all outside the region) is left where it is.
 */
export function focusIsFree(region: HTMLElement): boolean {
  const active = document.activeElement
  if (!active || active === document.body || active === document.documentElement) return true
  if (!region.contains(active)) return false
  return !takesTyping(active)
}

/**
 * Focus `element` as a landmark of the new phase: made programmatically focusable
 * (tabindex -1, so Tab does not stop on it afterwards) and focused without scrolling.
 */
export function focusTitle(element: HTMLElement) {
  if (!element.hasAttribute("tabindex")) element.tabIndex = -1
  element.focus({ preventScroll: true })
}

/**
 * After each phase swap, send focus to the new phase's title (F2).
 *
 * Every game swaps its phase in place (`useViewTransitionValue`): the button the player
 * just pressed ("Lock in", their vote, "Next question") is unmounted with the old phase,
 * focus fell to `<body>`, and the next Tab restarted at the skip link at the top of the
 * page. A screen reader lost its place at every round and never reached the colophon.
 *
 * - `phase` is the key of what is on screen (pass the SHOWN phase, after the view
 *   transition, so the new phase's DOM is there). The first render never moves focus,
 *   and neither does the page's first state arriving (a change from `null`/`undefined`):
 *   that is a page load, where focus stays at the top.
 * - The target is `targets[phase]`, else `fallback` (`"h2"`), searched in `regionRef`.
 * - Focus moves only when it is free (`focusIsFree`): on `<body>`, or on a control inside
 *   the game region. A player typing (the Kalimat answer, a description, the chat) keeps
 *   their field.
 */
export function usePhaseFocus(phase: unknown, regionRef: RefObject<HTMLElement | null>, options: PhaseFocusOptions = {}) {
  const previousRef = useRef(phase)
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    const previous = previousRef.current
    previousRef.current = phase
    if (Object.is(previous, phase) || previous == null || phase == null) return
    const region = regionRef.current
    if (!region || !focusIsFree(region)) return
    const { targets, fallback = DEFAULT_TARGET } = optionsRef.current
    const selector = targets?.[String(phase)] ?? fallback
    const target = region.querySelector<HTMLElement>(selector)
    if (target) focusTitle(target)
  }, [phase, regionRef])
}
