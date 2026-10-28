import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ColophonMeta, colophonOf, formatLasted, gameSeconds } from "../ColophonMeta"

describe("ColophonMeta", () => {
  it("reads game · host's majlis · count · duration from the server's fields (sketch H)", () => {
    // Act
    const { container } = render(
      <p>
        <ColophonMeta
          game="Undercover"
          host="Yusuf"
          count="3 rounds"
          startedAt="2026-10-28T20:00:00+00:00"
          endedAt="2026-10-28T20:21:40+00:00"
        />
      </p>,
    )

    // Assert
    expect(container.textContent).toBe("Undercover · game.colophon.majlis · 3 rounds · game.colophon.lasted21:40")
    const clock = screen.getByTestId("colophon-duration")
    expect(clock).toHaveAttribute("dateTime", "PT1300S")
    expect(clock).toHaveAttribute("aria-hidden", "true")
  })

  it("leaves out what the state does not carry (no host, game still running)", () => {
    const { container } = render(
      <p>
        <ColophonMeta game="Kalimat" count="7 rounds" startedAt="2026-10-28T20:00:00+00:00" endedAt={null} />
      </p>,
    )
    expect(container.textContent).toBe("Kalimat · 7 rounds")
    expect(screen.queryByTestId("colophon-duration")).not.toBeInTheDocument()
  })
})

describe("colophon helpers", () => {
  it("measures the game between its start and end", () => {
    expect(gameSeconds("2026-10-28T20:00:00Z", "2026-10-28T20:21:40Z")).toBe(1300)
    expect(gameSeconds("2026-10-28T20:00:00Z", null)).toBeNull()
    expect(gameSeconds("2026-10-28T20:10:00Z", "2026-10-28T20:00:00Z")).toBeNull()
  })

  it("writes the duration as a clock, with hours past the hour", () => {
    expect(formatLasted(1300)).toBe("21:40")
    expect(formatLasted(59)).toBe("0:59")
    expect(formatLasted(3725)).toBe("1:02:05")
  })

  it("takes the colophon fields off any game state", () => {
    expect(colophonOf({ host_username: "Yusuf", started_at: "a", ended_at: null })).toEqual({ hostUsername: "Yusuf", startedAt: "a", endedAt: null })
    expect(colophonOf(undefined)).toEqual({ hostUsername: undefined, startedAt: undefined, endedAt: undefined })
  })
})
