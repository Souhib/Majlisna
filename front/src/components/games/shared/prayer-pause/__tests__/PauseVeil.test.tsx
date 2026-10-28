import { act, fireEvent, render, screen } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import { StrictMode, useRef } from "react"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import type { GamePause } from "@/api/generated"
import en from "@/i18n/locales/en.json"
import { formatWallClock } from "../pause-utils"
import { PauseLayer } from "../PauseVeil"

// The real English strings (the setup file mocks react-i18next to print keys): the tests
// read what the table reads, and a missing key fails.
vi.unmock("react-i18next")

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

const SINCE = "2026-10-28T15:00:00.000Z"

function makePause(over: Partial<GamePause> = {}): GamePause {
  return {
    by_user_id: "host-1",
    by_username: "Yusuf",
    since: SINCE,
    reason: "salah",
    remaining_seconds: 42,
    paused_for_seconds: 230,
    anyone_can_resume_at: "2026-10-28T15:45:00.000Z",
    ...over,
  }
}

describe("PauseLayer (the prayer pause veil)", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("says why, who and for how long, as a dialog named by its title", () => {
    render(<PauseLayer pause={makePause()} canResume={false} onResume={() => {}} currentUserId="me" />)

    const dialog = screen.getByRole("dialog", { name: "The majlis pauses for ṣalāh" })
    expect(dialog).toHaveAccessibleDescription("Paused by \u2068Yusuf\u2069 · 3 min")
    // the Arabic name rides above the title in English, hidden from assistive tech
    expect(screen.getByText("وقفة الصلاة")).toHaveAttribute("aria-hidden", "true")
  })

  it("names the host who paused as 'you'", () => {
    render(<PauseLayer pause={makePause({ paused_for_seconds: 10 })} canResume onResume={() => {}} currentUserId="host-1" isHost />)

    expect(screen.getByRole("dialog")).toHaveAccessibleDescription("Paused by you · just now")
  })

  it("advances the minutes on this device from the server's paused_for_seconds", () => {
    render(<PauseLayer pause={makePause({ paused_for_seconds: 230 })} canResume={false} onResume={() => {}} />)
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription("Paused by \u2068Yusuf\u2069 · 3 min")

    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(screen.getByRole("dialog")).toHaveAccessibleDescription("Paused by \u2068Yusuf\u2069 · 4 min")
  })

  it("shows the clock frozen at the server's countdown, and it does not tick", () => {
    render(<PauseLayer pause={makePause({ remaining_seconds: 42 })} canResume={false} onResume={() => {}} clockTotal={60} />)

    const clock = screen.getByTestId("pause-clock")
    expect(clock).toHaveTextContent("0:42")
    expect(clock).toHaveTextContent("The clock stopped with 0:42 left")

    act(() => {
      vi.advanceTimersByTime(30_000)
    })

    expect(clock).toHaveTextContent("0:42")
    expect(clock.querySelector(".thread-clock")).toHaveAttribute("data-phase", "running")
  })

  it("draws no clock when the paused phase had none", () => {
    render(<PauseLayer pause={makePause({ remaining_seconds: null })} canResume={false} onResume={() => {}} />)

    expect(screen.queryByTestId("pause-clock")).toBeNull()
  })

  it("offers Resume to whoever may resume", () => {
    const onResume = vi.fn()
    render(<PauseLayer pause={makePause()} canResume onResume={onResume} isHost />)

    fireEvent.click(screen.getByRole("button", { name: "Resume" }))

    expect(onResume).toHaveBeenCalledTimes(1)
    // the host needs no explanation
    expect(screen.queryByText(/any player may resume/)).toBeNull()
  })

  it("tells a player why they may resume a pause that has run long", () => {
    render(<PauseLayer pause={makePause({ paused_for_seconds: 46 * 60 })} canResume onResume={() => {}} />)

    expect(screen.getByText("The pause has run long: any player may resume.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument()
  })

  it("otherwise says the host resumes, and from when anyone can", () => {
    render(<PauseLayer pause={makePause()} canResume={false} onResume={() => {}} />)

    expect(screen.queryByRole("button")).toBeNull()
    const time = formatWallClock("2026-10-28T15:45:00.000Z")
    const note = screen.getByText((_, el) => el?.tagName === "P" && el.textContent === `The host resumes; anyone can resume from ${time}.`)
    expect(note).toBeInTheDocument()
    // the time reads left to right in every language
    expect(screen.getByText(time)).toHaveAttribute("dir", "ltr")
  })

  it("promises a spectator no time: they never resume", () => {
    render(<PauseLayer pause={makePause()} canResume={false} onResume={() => {}} isSpectator />)

    expect(screen.getByText("The host resumes the game.")).toBeInTheDocument()
  })

  it("asks the server again once the pause stops being the host's alone", () => {
    // 44 of the 45 minutes have passed on the server's clock: one minute to go.
    const onRefresh = vi.fn()
    render(<PauseLayer pause={makePause({ paused_for_seconds: 44 * 60 })} canResume={false} onResume={() => {}} onRefresh={onRefresh} />)

    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(onRefresh).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(1_500)
    })
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it("takes focus when focus was in the game (or nowhere)", () => {
    render(<PauseLayer pause={makePause()} canResume={false} onResume={() => {}} />)

    expect(screen.getByRole("dialog")).toHaveFocus()
  })

  it("leaves focus where it is outside the game, and says it once instead", () => {
    // Prepare: the player is in the nav when the host pauses
    const nav = document.createElement("button")
    nav.textContent = "Rooms"
    document.body.appendChild(nav)
    nav.focus()
    const { rerender } = render(<PauseLayer pause={null} canResume={false} onResume={() => {}} />)

    // Act
    rerender(<PauseLayer pause={makePause()} canResume={false} onResume={() => {}} />)

    // Assert
    expect(nav).toHaveFocus()
    expect(screen.getByRole("status")).toHaveTextContent("The majlis pauses for ṣalāh. Paused by \u2068Yusuf\u2069.")
    nav.remove()
  })

  it.each([false, true])("gives focus back on resume to what had it in the game (StrictMode: %s)", (strict) => {
    // Prepare: a player typing their answer when the host pauses
    function Inner({ pause }: { pause: GamePause | null }) {
      const gameRef = useRef<HTMLDivElement>(null)
      return (
        <>
          <div ref={gameRef} tabIndex={-1}>
            <input aria-label="Your answer" />
          </div>
          <PauseLayer pause={pause} canResume={false} onResume={() => {}} gameRef={gameRef} />
        </>
      )
    }
    const Page = ({ pause }: { pause: GamePause | null }) =>
      strict ? (
        <StrictMode>
          <Inner pause={pause} />
        </StrictMode>
      ) : (
        <Inner pause={pause} />
      )
    const { rerender } = render(<Page pause={null} />)
    const input = screen.getByLabelText("Your answer")
    input.focus()

    // Act: paused, then resumed
    rerender(<Page pause={makePause()} />)
    act(() => {
      vi.runOnlyPendingTimers()
    })
    expect(screen.getByRole("dialog")).toHaveFocus()
    rerender(<Page pause={null} />)
    act(() => {
      vi.runOnlyPendingTimers()
    })

    // Assert
    expect(input).toHaveFocus()
  })

  it("says once that the game resumes, and the veil is gone", () => {
    const { rerender } = render(<PauseLayer pause={makePause()} canResume onResume={() => {}} />)
    expect(screen.getByTestId("pause-veil")).toBeInTheDocument()

    rerender(<PauseLayer pause={null} canResume={false} onResume={() => {}} />)

    expect(screen.queryByTestId("pause-veil")).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent("The game resumes.")
  })

  it("is drawn in the system: no red, no glow, no gradient", () => {
    render(<PauseLayer pause={makePause()} canResume onResume={() => {}} />)

    expect(screen.getByTestId("pause-veil").outerHTML).not.toMatch(/red-|destructive|gradient|shadow|blur|pulse/)
  })
})
