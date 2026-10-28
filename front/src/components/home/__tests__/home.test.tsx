import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { RoomPlayerState } from "@/api/generated/types/RoomPlayerState"
import { seatRoom } from "../HalqaCard"
import { HeroJoinForm } from "../HeroJoinForm"

const navigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
}))

const player = (over: Partial<RoomPlayerState>): RoomPlayerState => ({
  user_id: "u",
  username: "name",
  is_connected: true,
  is_disconnected: false,
  is_host: false,
  is_spectator: false,
  ...over,
})

describe("seatRoom", () => {
  it("puts the host at the ṣadr, marks the viewer, and keeps spectators off the ring", () => {
    // Prepare
    const players = [
      player({ user_id: "a", username: "Maryam" }),
      player({ user_id: "h", username: "Yusuf", is_host: true }),
      player({ user_id: "s", username: "Sumayya", is_spectator: true }),
      player({ user_id: "k", username: "Khadija", is_disconnected: true }),
    ]

    // Act
    const seating = seatRoom(players, "undercover", "a", { host: "host", you: "you" })

    // Assert
    expect(seating.seats.map((s) => s.name)).toEqual(["Yusuf", "Maryam", "Khadija"])
    expect(seating.seats[0]).toMatchObject({ state: "host", sub: "host" })
    expect(seating.seats[1]).toMatchObject({ me: true, sub: "you", state: "in" })
    expect(seating.seats[2].state).toBe("away")
    expect(seating.spectators).toEqual(["Sumayya"])
    expect(seating.hostName).toBe("Yusuf")
    expect(seating.quorum).toBe(3)
  })

  it("leaves open seats to fill without passing the game's capacity or the ring's twelve", () => {
    // Prepare
    const two = [player({ user_id: "h", is_host: true }), player({ user_id: "b" })]
    const eleven = Array.from({ length: 11 }, (_, i) => player({ user_id: String(i), is_host: i === 0 }))

    // Act / Assert
    expect(seatRoom(two, "codenames", undefined, { host: "", you: "" }).capacity).toBe(6)
    expect(seatRoom(eleven, "codenames", undefined, { host: "", you: "" }).capacity).toBe(10)
    expect(seatRoom(eleven, "word_quiz", undefined, { host: "", you: "" }).capacity).toBe(12)
    expect(seatRoom(two, null, undefined, { host: "", you: "" }).quorum).toBeUndefined()
  })

  it("clips a long name on the ring", () => {
    const [seat] = seatRoom([player({ username: "abcdefghijklmnop", is_host: true })], "mcq_quiz", undefined, {
      host: "",
      you: "",
    }).seats
    expect(seat.name).toBe("abcdefghijk…")
  })
})

describe("HeroJoinForm", () => {
  beforeEach(() => navigate.mockReset())

  it("says what is missing instead of submitting half a code", () => {
    // Prepare
    const { container } = render(<HeroJoinForm />)
    fireEvent.change(container.querySelector("#home-room-code") as HTMLInputElement, { target: { value: "lul" } })

    // Act
    fireEvent.click(screen.getByRole("button", { name: "home.join.submit" }))

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("home.join.incomplete")
    expect(navigate).not.toHaveBeenCalled()
  })

  it("hands a full code and PIN to the share-link route, which joins (through the login if needed)", () => {
    // Prepare
    const { container } = render(<HeroJoinForm />)
    fireEvent.change(container.querySelector("#home-room-code") as HTMLInputElement, { target: { value: "lulim" } })
    const pin = screen.getAllByRole("textbox", { name: /home\.join\.pinDigit/ })
    fireEvent.paste(pin[0], { clipboardData: { getData: () => "6981" } })

    // Act
    fireEvent.click(screen.getByRole("button", { name: "home.join.submit" }))

    // Assert
    expect(navigate).toHaveBeenCalledWith({ to: "/rooms/join", search: { code: "LULIM", pin: "6981" } })
  })
})
