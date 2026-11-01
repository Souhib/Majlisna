import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The last 30 days on /stats, drawn with the page's own elements (FP-17: chart.js was 52 kB
 * gzip for one bar chart). One bar per day, wins at the foot, losses above them, all on one
 * scale; the numbers themselves are in the screen-reader table.
 */
const historyHook = vi.hoisted(() => vi.fn())
vi.mock("@/api/generated", () => ({
  useGetGameHistoryApiV1StatsUsersUserIdHistoryGet: (...args: unknown[]) => historyHook(...args),
}))

const { WinLossChart } = await import("../WinLossChart")

/** The UTC calendar day `daysAgo` days before today, as the history endpoint names it. */
function day(daysAgo: number): string {
  const now = new Date()
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - daysAgo * 86_400_000).toISOString().slice(0, 10)
}

function bars(container: HTMLElement) {
  return [...container.querySelectorAll<HTMLElement>("[data-day]")]
}

describe("WinLossChart", () => {
  beforeEach(() => {
    historyHook.mockReset()
  })

  it("draws one bar per day of the last 30, whatever the endpoint listed", () => {
    // Prepare: two days with games, out of thirty
    historyHook.mockReturnValue({
      data: [
        { date: day(0), wins: 2, losses: 1 },
        { date: day(10), wins: 0, losses: 4 },
      ],
      isLoading: false,
    })

    // Act
    const { container } = render(<WinLossChart userId="u1" />)

    // Assert: thirty bars, oldest first, today last
    const drawn = bars(container)
    expect(drawn).toHaveLength(30)
    expect(drawn[0].dataset.day).toBe(day(29))
    expect(drawn[29].dataset.day).toBe(day(0))
  })

  it("puts every bar on one scale: wins and losses in proportion to the busiest day", () => {
    // Prepare: the busiest day has 4 games
    historyHook.mockReturnValue({
      data: [
        { date: day(0), wins: 2, losses: 1 },
        { date: day(10), wins: 0, losses: 4 },
      ],
      isLoading: false,
    })

    // Act
    const { container } = render(<WinLossChart userId="u1" />)
    const today = bars(container).find((b) => b.dataset.day === day(0))
    const busiest = bars(container).find((b) => b.dataset.day === day(10))
    const quiet = bars(container).find((b) => b.dataset.day === day(5))

    // Assert: heights are shares of the top of the scale (4)
    expect(today?.querySelector<HTMLElement>("[data-part=won]")?.style.height).toBe("50%")
    expect(today?.querySelector<HTMLElement>("[data-part=lost]")?.style.height).toBe("25%")
    expect(busiest?.querySelector<HTMLElement>("[data-part=lost]")?.style.height).toBe("100%")
    expect(busiest?.querySelector("[data-part=won]")).toBeNull()
    expect(quiet?.querySelector("[data-part]")).toBeNull()
  })

  it("names a day's games on hover", () => {
    // Prepare
    historyHook.mockReturnValue({ data: [{ date: day(0), wins: 2, losses: 1 }], isLoading: false })
    const { container } = render(<WinLossChart userId="u1" />)
    const today = bars(container).find((b) => b.dataset.day === day(0)) as HTMLElement

    // Act
    fireEvent.pointerEnter(today)

    // Assert: the tip says the day's figures
    const tip = screen.getByTestId("winloss-tip")
    expect(tip).toHaveTextContent("stats.won")
    expect(tip).toHaveTextContent("2")
    expect(tip).toHaveTextContent("stats.lost")
    expect(tip).toHaveTextContent("1")

    // Act: the pointer leaves
    fireEvent.pointerLeave(today)

    // Assert
    expect(screen.queryByTestId("winloss-tip")).not.toBeInTheDocument()

    // Act: a day without a game (no bar there)
    fireEvent.pointerEnter(bars(container).find((b) => b.dataset.day === day(4)) as HTMLElement)

    // Assert: nothing to name
    expect(screen.queryByTestId("winloss-tip")).not.toBeInTheDocument()
  })

  it("says so when no game was played in the last 30 days, with no bars", () => {
    // Prepare
    historyHook.mockReturnValue({ data: [], isLoading: false })

    // Act
    const { container } = render(<WinLossChart userId="u1" />)

    // Assert
    expect(screen.getByText("stats.noRecentGames")).toBeInTheDocument()
    expect(bars(container)).toHaveLength(0)
  })

  it("keeps the figures in a table for assistive tech, one row per day played", () => {
    // Prepare
    historyHook.mockReturnValue({
      data: [
        { date: day(0), wins: 2, losses: 1 },
        { date: day(10), wins: 0, losses: 4 },
      ],
      isLoading: false,
    })

    // Act
    render(<WinLossChart userId="u1" />)

    // Assert
    const table = screen.getByRole("table")
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2)
    expect(screen.getByRole("img", { name: /stats.last30/ })).toBeInTheDocument()
  })
})
