import { vi, type Mock } from "vitest"

/**
 * happy-dom has no Web Animations: `Element.animate` is a recording fake here (the
 * ThreadClock test's pattern). Each call keeps the element, its keyframes and timing.
 */
export interface RecordedAnimation {
  el: HTMLElement
  keyframes: Keyframe[]
  options: KeyframeAnimationOptions
  anim: { id: string; cancel: Mock; finish: Mock }
}

export const calls: RecordedAnimation[] = []

export function recordAnimations() {
  calls.length = 0
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    writable: true,
    value: vi.fn(function (this: HTMLElement, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
      const anim = { id: "", cancel: vi.fn(), finish: vi.fn() }
      calls.push({ el: this, keyframes, options, anim })
      return anim
    }),
  })
}

export function stopRecordingAnimations() {
  delete (HTMLElement.prototype as { animate?: unknown }).animate
  vi.unstubAllGlobals()
}

/** The animations run on the parts (`data-erase`) of one seat. */
export function animationsOf(seat: Element | null, part?: string) {
  return calls.filter((c) => !!seat && seat.contains(c.el) && (part === undefined || c.el.dataset.erase === part))
}

export function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}
