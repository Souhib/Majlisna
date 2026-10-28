import { describe, expect, it } from "vitest"
import { awayCountdown, awayLabel, isGameType, type LobbyMember, ringName, rosterEvents, seatLobby, stableOrder, tableState, toMembers } from "./lobby"

const labels = { you: "you", host: "host", youHost: "you · host", away: "away" }

function member(id: string, extra: Partial<LobbyMember> = {}): LobbyMember {
  return { id, username: id.toUpperCase(), isHost: false, isSpectator: false, isAway: false, awaySecondsLeft: null, ...extra }
}

describe("toMembers", () => {
  it("maps room state players and marks the owner as host", () => {
    // Prepare
    const players = [
      { user_id: "a", username: "Yusuf", is_spectator: false, is_disconnected: false },
      { user_id: "b", username: "Khadija", is_spectator: false, is_disconnected: true, away_seconds_left: 598 },
      { user_id: "c", username: "Sumayya", is_spectator: true, is_disconnected: false },
    ]

    // Act
    const members = toMembers(players, "a")

    // Assert
    expect(members).toEqual([
      { id: "a", username: "Yusuf", isHost: true, isSpectator: false, isAway: false, awaySecondsLeft: null },
      { id: "b", username: "Khadija", isHost: false, isSpectator: false, isAway: true, awaySecondsLeft: 598 },
      { id: "c", username: "Sumayya", isHost: false, isSpectator: true, isAway: false, awaySecondsLeft: null },
    ])
  })

  it("returns an empty roster for a malformed payload", () => {
    expect(toMembers(undefined, "a")).toEqual([])
    expect(toMembers({ players: [] }, "a")).toEqual([])
  })
})

describe("seatLobby", () => {
  it("puts the host at the sadr, keeps spectators off the ring and labels the seats", () => {
    // Prepare
    const members = [member("b"), member("a", { isHost: true }), member("c", { isAway: true }), member("d", { isSpectator: true })]

    // Act
    const seating = seatLobby(members, "undercover", "b", labels)

    // Assert
    expect(seating.seats.map((s) => [s.id, s.state, s.sub, s.me])).toEqual([
      ["a", "host", "host", false],
      ["b", "in", "you", true],
      ["c", "away", "away", false],
    ])
    expect(seating.spectators.map((m) => m.id)).toEqual(["d"])
    expect(seating.seated.map((m) => m.id)).toEqual(["a", "b", "c"])
    expect(seating.quorum).toBe(3)
  })

  it("shows the viewer-host as 'you · host'", () => {
    const seating = seatLobby([member("a", { isHost: true })], "word_quiz", "a", labels)
    expect(seating.seats[0].sub).toBe("you · host")
  })

  it("draws three open seats after five players, as in the sketch", () => {
    const members = ["a", "b", "c", "d", "e"].map((id, i) => member(id, { isHost: i === 0 }))
    expect(seatLobby(members, "undercover", "a", labels).capacity).toBe(8)
  })

  it("never draws more seats than the game holds or the ring can show", () => {
    const nine = Array.from({ length: 9 }, (_, i) => member(`p${i}`, { isHost: i === 0 }))
    const twelve = Array.from({ length: 12 }, (_, i) => member(`p${i}`, { isHost: i === 0 }))
    expect(seatLobby(nine, "codenames", "p0", labels).capacity).toBe(10)
    expect(seatLobby(twelve, "undercover", "p0", labels).capacity).toBe(12)
    expect(seatLobby([member("a", { isHost: true })], "mcq_quiz", "a", labels).capacity).toBe(6)
  })

  it("clips long names on the ring only", () => {
    const seating = seatLobby([member("a", { isHost: true, username: "Abdurrahman_al_Andalusi" })], "undercover", "a", labels)
    expect(seating.seats[0].name).toBe("Abdurrahm…")
    expect(seating.seated[0].username).toBe("Abdurrahman_al_Andalusi")
  })
})

describe("stableOrder", () => {
  it("keeps first-seen order, drops leavers and appends newcomers", () => {
    // Prepare: the server now lists c before a, b left, d arrived
    const order = ["a", "b", "c"]
    const members = [member("c"), member("d"), member("a")]

    // Act
    const next = stableOrder(order, members)

    // Assert
    expect(next).toEqual(["a", "c", "d"])
  })

  it("seats players in that order whatever the server's order", () => {
    const members = [member("c"), member("host", { isHost: true }), member("a")]
    const seating = seatLobby(members, "undercover", "host", labels, ["host", "a", "c"])
    expect(seating.seats.map((s) => s.id)).toEqual(["host", "a", "c"])
  })
})

describe("ringName", () => {
  it("keeps short names and counts code points, not UTF-16 units", () => {
    expect(ringName("Maryam")).toBe("Maryam")
    expect(ringName("عبدالرحمن")).toBe("عبدالرحمن")
  })
})

describe("tableState", () => {
  it("names how many players are missing", () => {
    expect(tableState(1, "undercover")).toEqual({ kind: "short", missing: 2 })
    expect(tableState(3, "codenames")).toEqual({ kind: "short", missing: 1 })
  })

  it("is ready between the floor and the ceiling", () => {
    expect(tableState(3, "undercover")).toEqual({ kind: "ready" })
    expect(tableState(1, "word_quiz")).toEqual({ kind: "ready" })
    expect(tableState(40, "mcq_quiz")).toEqual({ kind: "ready" })
  })

  it("refuses a table larger than the game holds", () => {
    expect(tableState(11, "codenames")).toEqual({ kind: "over", max: 10 })
    expect(tableState(13, "undercover")).toEqual({ kind: "over", max: 12 })
  })
})

describe("rosterEvents", () => {
  it("treats the first roster as the baseline", () => {
    expect(rosterEvents([], [member("a"), member("b")], "a")).toEqual([])
  })

  it("reports arrivals, spectators, departures and connection changes, never the viewer's own", () => {
    // Prepare
    const prev = [member("me", { isHost: true }), member("b"), member("c", { isAway: true }), member("d")]
    const next = [member("me", { isHost: true }), member("b", { isAway: true }), member("c"), member("e"), member("f", { isSpectator: true })]

    // Act
    const events = rosterEvents(prev, next, "me")

    // Assert
    expect(events).toEqual([
      { kind: "away", name: "B" },
      { kind: "back", name: "C" },
      { kind: "joined", name: "E" },
      { kind: "watching", name: "F" },
      { kind: "left", name: "D" },
    ])
  })

  it("ignores a spectator's connection changes", () => {
    const prev = [member("me", { isHost: true }), member("s", { isSpectator: true, isAway: true })]
    const next = [member("me", { isHost: true }), member("s", { isSpectator: true })]
    expect(rosterEvents(prev, next, "me")).toEqual([])
  })

  it("reports a new host, even when it is the viewer", () => {
    const prev = [member("a", { isHost: true }), member("me")]
    const next = [member("me", { isHost: true })]
    expect(rosterEvents(prev, next, "me")).toEqual([
      { kind: "left", name: "A" },
      { kind: "host", name: "ME" },
    ])
  })
})

describe("isGameType", () => {
  it("accepts the four games only", () => {
    expect(isGameType("codenames")).toBe(true)
    expect(isGameType("chess")).toBe(false)
    expect(isGameType(null)).toBe(false)
  })
})

describe("away countdown", () => {
  it("counts each away seat down from the server's figure, from the moment it arrived", () => {
    // Prepare
    const members = [
      member("a", { isHost: true }),
      member("b", { isAway: true, awaySecondsLeft: 598 }),
      member("c", { isAway: true, awaySecondsLeft: 3 }),
      member("d", { isAway: true }), // no countdown sent: no clock
    ]
    const receivedAt = 1_000_000

    // Act
    const atOnce = awayCountdown(members, receivedAt, receivedAt + 400)
    const later = awayCountdown(members, receivedAt, receivedAt + 5_000)

    // Assert
    expect(Object.fromEntries(atOnce)).toEqual({ b: 598, c: 3 })
    expect(Object.fromEntries(later)).toEqual({ b: 593, c: 0 })
  })

  it("never runs ahead when the clock reads before the state's arrival", () => {
    const left = awayCountdown([member("b", { isAway: true, awaySecondsLeft: 60 })], 2_000, 1_500)
    expect(left.get("b")).toBe(60)
  })

  it("writes the away label with its clock, or alone", () => {
    expect(awayLabel("away", 598)).toBe("away · 9:58")
    expect(awayLabel("away", 0)).toBe("away · 0:00")
    expect(awayLabel("away", undefined)).toBe("away")
  })

  it("puts the countdown under an away seat on the ring", () => {
    // Prepare
    const members = [member("a", { isHost: true }), member("b", { isAway: true, awaySecondsLeft: 598 })]

    // Act
    const { seats } = seatLobby(members, "undercover", "a", labels, undefined, new Map([["b", 598]]))

    // Assert
    expect(seats.find((s) => s.id === "b")).toMatchObject({ state: "away", sub: "away · 9:58" })
  })
})
