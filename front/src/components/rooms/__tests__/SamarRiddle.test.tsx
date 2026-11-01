import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import { afterEach, beforeAll, beforeEach, describe, expect, it, type Mock, vi } from "vitest"
import type { RoomRiddle } from "@/api/generated"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import en from "@/i18n/locales/en.json"
import { ease, inkDuration } from "@/lib/motion"
import { gameRiddleScope, LOBBY_RIDDLE_SCOPE, readRiddleRecord, type RiddleRecord, writeRiddleRecord } from "../samar-riddle"
import { RIDDLE_INK_ID, SamarRiddle } from "../SamarRiddle"

/**
 * The samar riddle on the real generated hook over the fake client, with the real English
 * strings. happy-dom has no Web Animations, so `Element.animate` is a recording fake: the
 * line is written in (two transforms, the window and the text) only when it CHANGES, never
 * on the first riddle a panel shows; reduced motion and a line naming Allah fade.
 */
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.unmock("react-i18next")

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

const RIDDLE = "GET /api/v1/rooms/room-1/riddle"

const riddle = (id: string, hint: string, over: Partial<RoomRiddle> = {}): RoomRiddle => ({
  id,
  category: "prophets",
  hint,
  answer: { word_display: "Ibrahim / Abraham", word_ar: "إبراهيم", word_ar_vocalized: null },
  ...over,
})

interface AnimateCall {
  el: Element
  keyframes: Keyframe[]
  options: KeyframeAnimationOptions
}
let calls: AnimateCall[] = []

function stubReducedMotion(reduce: boolean) {
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

function renderRiddle(props: Partial<Parameters<typeof SamarRiddle>[0]> = {}) {
  const queryClient = new QueryClient()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SamarRiddle roomId="room-1" scope={LOBBY_RIDDLE_SCOPE} waitKey={LOBBY_RIDDLE_SCOPE} note="lobby" {...props} />
    </QueryClientProvider>,
  )
  return { queryClient, ...view }
}

/** A riddle already on screen in this tab, shown `agoMs` before now. */
function stored(id: string, hint: string, agoMs: number, over: Partial<NonNullable<RiddleRecord["current"]>> = {}, scope = LOBBY_RIDDLE_SCOPE) {
  writeRiddleRecord("room-1", scope, {
    current: { riddle: riddle(id, hint), lang: "en", waitKey: LOBBY_RIDDLE_SCOPE, shownAt: Date.now() - agoMs, revealed: false, ...over },
    last: null,
  })
}

const inkCalls = () => calls.filter((c) => c.options.id === RIDDLE_INK_ID)

beforeEach(() => {
  resetFakeApi()
  sessionStorage.clear()
  calls = []
  stubReducedMotion(false)
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    writable: true,
    value: vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
      calls.push({ el: this, keyframes, options })
      return { id: options?.id ?? "", cancel: vi.fn(), finished: Promise.resolve() }
    }),
  })
})

afterEach(() => {
  delete (HTMLElement.prototype as { animate?: unknown }).animate
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.documentElement.removeAttribute("dir")
})

describe("SamarRiddle, the riddle while the table waits", () => {
  it("asks once, in the player's language, and puts rung 1 under the theme's question", async () => {
    // Prepare
    answer(RIDDLE, () => riddle("w1", "A great patriarch"))

    // Act
    renderRiddle()

    // Assert: the question and the rung, the answer kept back, nothing animated
    expect(await screen.findByText("A great patriarch")).toBeInTheDocument()
    expect(screen.getByText("While you wait: who is it?")).toBeInTheDocument()
    expect(screen.getByText("The answer in a moment, or after the game.")).toBeInTheDocument()
    expect(screen.queryByText(/Ibrahim/)).toBeNull()
    expect(requestsTo(RIDDLE)).toHaveLength(1)
    expect(requestsTo(RIDDLE)[0].params).toEqual({ lang: "en" })
    expect(inkCalls()).toHaveLength(0)
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE).current?.riddle.id).toBe("w1")
  })

  it("asks where for a place and what for anything else", async () => {
    // Prepare
    answer(RIDDLE, () => riddle("w2", "A city of the Hijaz", { category: "places" }))

    // Act
    renderRiddle()

    // Assert
    expect(await screen.findByText("While you wait: where is it?")).toBeInTheDocument()
  })

  it("keeps its riddle across a remount or a reload: no second request, no new riddle", async () => {
    // Prepare
    answer(RIDDLE, () => riddle("w1", "A great patriarch"))
    const first = renderRiddle()
    await screen.findByText("A great patriarch")
    first.unmount()
    answer(RIDDLE, () => riddle("w9", "Another line"))

    // Act
    renderRiddle()

    // Assert
    expect(screen.getByText("A great patriarch")).toBeInTheDocument()
    expect(requestsTo(RIDDLE)).toHaveLength(1)
  })

  it("offers the answer on a tap 30 s after it was first shown, and only then", () => {
    // Prepare: shown 29 s ago in this tab
    vi.useFakeTimers()
    stored("w1", "A great patriarch", 29_000)
    renderRiddle()
    expect(screen.queryByRole("button", { name: "Show the answer" })).toBeNull()

    // Act
    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    fireEvent.click(screen.getByRole("button", { name: "Show the answer" }))

    // Assert: the answer, in the interface language and in Arabic, with focus on it
    const answerLine = screen.getByText(/It was/)
    expect(answerLine.textContent).toBe("It was Ibrahim / Abraham · إبراهيم")
    expect(screen.getByText("إبراهيم")).toHaveAttribute("lang", "ar")
    expect(document.activeElement).toBe(answerLine.closest("[tabindex]"))
    expect(screen.getByRole("button", { name: "Another riddle" })).toBeInTheDocument()
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE).current?.revealed).toBe(true)
    expect(requestsTo(RIDDLE)).toHaveLength(0)
  })

  it("a riddle that was due before the panel opened offers its answer at once", () => {
    // Prepare
    stored("w1", "A great patriarch", 31_000)

    // Act
    renderRiddle()

    // Assert
    expect(screen.getByRole("button", { name: "Show the answer" })).toBeInTheDocument()
  })

  it("writes the next riddle in (the ink, in the reading direction), never the first", async () => {
    // Prepare: an answered riddle, and the next one waiting on the server
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => riddle("w2", "A decisive early event in Islamic history"))
    renderRiddle()
    expect(inkCalls()).toHaveLength(0)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await screen.findByText("A decisive early event in Islamic history")

    // Assert: two compositor transforms in step, the window and the text, for a line's writing time
    const ink = inkCalls()
    expect(ink).toHaveLength(2)
    const duration = inkDuration("A decisive early event in Islamic history", "line") * 1000
    for (const call of ink) {
      expect(call.options.duration).toBe(duration)
      expect(call.options.easing).toBe(`cubic-bezier(${ease.ink.join(", ")})`)
      expect(call.keyframes.every((k) => Object.keys(k).every((p) => p === "transform" || p === "offset"))).toBe(true)
      expect(call.keyframes.at(-1)?.transform).toBe("translateX(0)")
    }
    expect(ink[0].keyframes[0].transform).toBe("translateX(-100%)")
    expect(ink[1].keyframes[0].transform).toBe("translateX(calc(100% + 1.25em))")
    expect(screen.queryByText(/It was/)).toBeNull()
    expect(requestsTo(RIDDLE)).toHaveLength(1)
    // the new line takes focus: the button pressed is gone
    expect(document.activeElement).toBe(screen.getByText("A decisive early event in Islamic history").closest("[tabindex]"))
  })

  it("starts the writing at the right edge in Arabic", async () => {
    // Prepare
    document.documentElement.setAttribute("dir", "rtl")
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => riddle("w2", "A decisive early event in Islamic history"))
    renderRiddle()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await screen.findByText("A decisive early event in Islamic history")

    // Assert
    const ink = inkCalls()
    expect(ink[0].keyframes[0].transform).toBe("translateX(100%)")
    expect(ink[1].keyframes[0].transform).toBe("translateX(calc(-100% - 1.25em))")
  })

  it("fades the new line under reduced motion", async () => {
    // Prepare
    stubReducedMotion(true)
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => riddle("w2", "A decisive early event in Islamic history"))
    renderRiddle()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await screen.findByText("A decisive early event in Islamic history")

    // Assert: opacity only, on the text
    const ink = inkCalls()
    expect(ink).toHaveLength(1)
    expect(ink[0].keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
  })

  it("never sweeps across a name of Allah: such a line fades in", async () => {
    // Prepare
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => riddle("w2", "A believer's direct line to Allah", { category: "islamic_concepts" }))
    renderRiddle()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await screen.findByText("A believer's direct line to Allah")

    // Assert
    const ink = inkCalls()
    expect(ink).toHaveLength(1)
    expect(ink[0].keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
  })

  it("fades a line that wraps: one window would uncover its lines all at once, a wipe and not a pen", async () => {
    // Prepare: at a phone's width the rung runs onto two lines (the range's line boxes)
    const rects = vi.spyOn(Range.prototype, "getClientRects").mockReturnValue([
      { top: 100, bottom: 128.5, height: 28.5, left: 0, right: 300, width: 300, x: 0, y: 100 },
      { top: 128.5, bottom: 157, height: 28.5, left: 0, right: 120, width: 120, x: 0, y: 128.5 },
    ] as unknown as DOMRectList)
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => riddle("w2", "Contains rules of Islamic manners and etiquette"))
    renderRiddle()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await screen.findByText("Contains rules of Islamic manners and etiquette")

    // Assert: the text fades in, nothing travels
    const ink = inkCalls()
    expect(ink).toHaveLength(1)
    expect(ink[0].keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(ink[0].el).toBe(screen.getByText("Contains rules of Islamic manners and etiquette"))
    rects.mockRestore()
  })

  it("still writes a line that holds on one line", async () => {
    // Prepare: one line box (two fragments on the same line are one line)
    const rects = vi.spyOn(Range.prototype, "getClientRects").mockReturnValue([
      { top: 100, bottom: 128.5, height: 28.5, left: 0, right: 200, width: 200, x: 0, y: 100 },
      { top: 100.4, bottom: 128.5, height: 28.1, left: 200, right: 300, width: 100, x: 200, y: 100.4 },
    ] as unknown as DOMRectList)
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => riddle("w2", "A unit of time"))
    renderRiddle()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await screen.findByText("A unit of time")

    // Assert
    expect(inkCalls()).toHaveLength(2)
    rects.mockRestore()
  })

  it("answers the riddle of the question before at the next one, and asks a new one", async () => {
    // Prepare: question 1's riddle, never revealed
    stored("w1", "A great patriarch", 10_000, { waitKey: "1" }, gameRiddleScope("g1"))
    answer(RIDDLE, () => riddle("w2", "A decisive early event in Islamic history"))

    // Act: the results of question 2
    renderRiddle({ scope: gameRiddleScope("g1"), waitKey: "2", note: "round" })

    // Assert
    expect(screen.getByText(/The last riddle/)).toHaveTextContent("The last riddle, “A great patriarch”, was Ibrahim / Abraham.")
    expect(await screen.findByText("A decisive early event in Islamic history")).toBeInTheDocument()
    expect(screen.getByText("The answer in a moment, or after the next question.")).toBeInTheDocument()
    expect(inkCalls()).toHaveLength(0)
  })

  it("after the last question, only answers the riddle before: nothing new is asked", () => {
    // Prepare
    stored("w1", "A great patriarch", 10_000, { waitKey: "9" }, gameRiddleScope("g1"))

    // Act
    renderRiddle({ scope: gameRiddleScope("g1"), waitKey: "10", note: "round", ask: false })

    // Assert
    expect(screen.getByText(/The last riddle/)).toBeInTheDocument()
    expect(screen.queryByText(/While you wait/)).toBeNull()
    expect(requestsTo(RIDDLE)).toHaveLength(0)
  })

  it("asks nothing and shows nothing when there is nothing to show", async () => {
    // Act
    const { container } = renderRiddle({ ask: false })
    await act(async () => {})

    // Assert
    expect(container).toBeEmptyDOMElement()
    expect(requestsTo(RIDDLE)).toHaveLength(0)
  })

  it("keeps the answer for after a Kalimat game: it could be one of its words", () => {
    // Prepare
    stored("w1", "A great patriarch", 40_000)

    // Act
    renderRiddle({ note: "kalimat" })

    // Assert
    expect(screen.getByText("The answer after the game: it could come up in Kalimat.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Show the answer" })).toBeNull()
  })

  it("says nothing when the server refuses a riddle: it is a pastime, never an error", async () => {
    // Prepare
    answer(RIDDLE, () => {
      throw httpError(409, { error_key: "errors.api.riddleNotDuringGame" })
    })

    // Act
    const { container } = renderRiddle()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    // Assert
    expect(requestsTo(RIDDLE)).toHaveLength(1)
    expect(container).toBeEmptyDOMElement()
  })

  it("keeps the old riddle when another one cannot be had", async () => {
    // Prepare
    stored("w1", "A great patriarch", 40_000, { revealed: true })
    answer(RIDDLE, () => {
      throw httpError(429, { error_key: "errors.api.rateLimitExceeded" })
    })
    renderRiddle()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Another riddle" }))
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    // Assert
    expect(screen.getByText("A great patriarch")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Another riddle" })).not.toBeDisabled()
    expect((HTMLElement.prototype.animate as Mock).mock.calls.length).toBe(0)
  })
})
