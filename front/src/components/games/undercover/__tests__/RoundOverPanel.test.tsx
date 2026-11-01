import { fireEvent, render, screen } from "@testing-library/react"
import i18next from "i18next"
import { initReactI18next } from "react-i18next"
import type { ComponentProps } from "react"
import { beforeAll, describe, expect, it, vi } from "vitest"
import en from "@/i18n/locales/en.json"
import { RoundOverPanel } from "../RoundOverPanel"

// The real English strings (the setup file mocks react-i18next to print keys): the E2E
// helpers read this screen's English text, so the tests read it too.
vi.unmock("react-i18next")

beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    interpolation: { escapeValue: false },
  })
})

const ROUND = {
  round: 2,
  votes: [
    { voter: "Maryam", voter_id: "u1", target: "Bilal", target_id: "u4" },
    { voter: "Idris", voter_id: "u2", target: "Bilal", target_id: "u4" },
  ],
  eliminated: { username: "Bilal", role: "civilian", user_id: "u4" },
}

type Props = ComponentProps<typeof RoundOverPanel>

function props(over: Partial<Props> = {}): Props {
  return {
    round: ROUND,
    roundNumber: 2,
    currentUserId: "u1",
    myWord: null,
    isHost: false,
    canMarkReady: true,
    isReady: false,
    readyCount: 0,
    readyQuorum: 3,
    isStarting: false,
    onNextRound: vi.fn(),
    ...over,
  }
}

/** Playwright's `text=Waiting for` is a case-insensitive substring match on any element. */
function expectNoWaitingFor() {
  expect(document.body.textContent ?? "").not.toMatch(/waiting for/i)
}

describe("RoundOverPanel: the ready quorum (owner rule (d))", () => {
  it("keeps 'Next round' for the host, who forces the round, and tells them where the table stands", () => {
    // Prepare
    const onNextRound = vi.fn()

    // Act
    render(<RoundOverPanel {...props({ isHost: true, canMarkReady: false, readyCount: 1, readyQuorum: 3, onNextRound })} />)
    fireEvent.click(screen.getByRole("button", { name: "Next round", exact: true }))

    // Assert: the button the E2E helper clicks is still exactly "Next round", and the only one
    expect(onNextRound).toHaveBeenCalledTimes(1)
    expect(screen.getAllByRole("button")).toHaveLength(1)
    expect(screen.queryByRole("button", { name: /ready/i })).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent("1 of 3 ready")
    expect(screen.getByTestId("elimination-overlay")).toBeInTheDocument()
    expectNoWaitingFor()
  })

  it("gives an alive player who is not the host 'I’m ready', which calls next-round, then the count", () => {
    // Prepare
    const onNextRound = vi.fn()
    const { rerender } = render(<RoundOverPanel {...props({ readyCount: 0, readyQuorum: 3, onNextRound })} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "I’m ready" }))

    // Assert: the same endpoint as the host's (the hook sends it), and no "Next round" here
    expect(onNextRound).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: /next round/i })).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent("0 of 3 ready")

    // Act: the state that comes back says this player is ready
    rerender(<RoundOverPanel {...props({ isReady: true, readyCount: 1, readyQuorum: 3, onNextRound })} />)

    // Assert: the button gives way to the line that says so, with the count
    expect(screen.queryByRole("button")).toBeNull()
    expect(screen.getByText("You are ready. The next round starts when everyone is, or when the host starts it.")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("1 of 3 ready")
    expect(screen.getByTestId("elimination-overlay")).toBeInTheDocument()
    expectNoWaitingFor()
  })

  it("hands the focus the button held to the line that replaces it, and takes none on a page loaded already marked", () => {
    // Prepare
    const { rerender, unmount } = render(<RoundOverPanel {...props()} />)
    screen.getByRole("button", { name: "I’m ready" }).focus()

    // Act: the mark is in, the button gives way
    rerender(<RoundOverPanel {...props({ isReady: true, readyCount: 1 })} />)

    // Assert
    const line = screen.getByText(/^You are ready\./).closest("p")
    expect(document.activeElement).toBe(line)
    unmount()

    // Act: a reload on a round this player had already marked
    render(<RoundOverPanel {...props({ isReady: true, readyCount: 1 })} />)

    // Assert
    expect(document.activeElement).toBe(document.body)
  })

  it("shows the busy button while the mark is on its way", () => {
    // Act
    render(<RoundOverPanel {...props({ isStarting: true })} />)

    // Assert
    expect(screen.getByRole("button", { name: /^I’m ready/ })).toHaveAttribute("aria-busy", "true")
  })

  it.each([
    ["an eliminated player", { canMarkReady: false }],
    ["a spectator", { canMarkReady: false, currentUserId: "spectator-1" }],
  ])("shows %s only the count", (_who, over) => {
    // Act
    render(<RoundOverPanel {...props({ ...over, readyCount: 2, readyQuorum: 3 })} />)

    // Assert: no button, no ready line, no "the host starts" either
    expect(screen.queryByRole("button")).toBeNull()
    expect(screen.queryByText(/You are ready/)).toBeNull()
    expect(screen.queryByText(/host starts/i)).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent("2 of 3 ready")
    expect(screen.getByTestId("elimination-overlay")).toBeInTheDocument()
    expectNoWaitingFor()
  })

  it("says nothing about a count while the server has not sent one", () => {
    // Act: an older state, without the ready fields
    render(<RoundOverPanel {...props({ canMarkReady: false, readyCount: 0, readyQuorum: 0 })} />)

    // Assert
    expect(screen.queryByRole("status")).toBeNull()
    expect(screen.queryByText(/of 0 ready/)).toBeNull()
  })

  it.each([
    ["the host", { isHost: true, canMarkReady: false }],
    ["a player not ready yet", {}],
    ["a ready player", { isReady: true, readyCount: 1 }],
    ["an eliminated player", { canMarkReady: false }],
  ])("never prints a line starting with 'Waiting for' for %s", (_who, over) => {
    // Act
    render(<RoundOverPanel {...props(over)} />)

    // Assert: the helpers read "Waiting for" as "this player has voted"
    for (const el of document.body.querySelectorAll("*")) {
      expect(el.textContent?.trim() ?? "").not.toMatch(/^waiting for/i)
    }
    expectNoWaitingFor()
  })
})
