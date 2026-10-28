import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Verdict, formatNames, groupVotes } from "./Verdict"

const votes = [
  { voter: "Maryam", voter_id: "u1", target: "Bilal", target_id: "u4" },
  { voter: "Idris", voter_id: "u2", target: "Bilal", target_id: "u4" },
  { voter: "Khadija", voter_id: "u3", target: "Idris", target_id: "u2" },
  { voter: "Bilal", voter_id: "u4", target: "Maryam", target_id: "u1" },
]

describe("groupVotes", () => {
  it("groups voters by target, the most voted first", () => {
    const groups = groupVotes(votes)
    expect(groups[0]).toEqual({ targetId: "u4", target: "Bilal", voters: ["Maryam", "Idris"] })
    expect(groups).toHaveLength(3)
  })
})

describe("formatNames", () => {
  it("joins names the way the language does", () => {
    expect(formatNames(["Maryam", "Idris", "Yusuf"], "en")).toBe("Maryam, Idris, and Yusuf")
    expect(formatNames(["Maryam", "Idris"], "fr")).toBe("Maryam et Idris")
  })
})

describe("Verdict", () => {
  it("names the player the table chose and turns their tablet over", () => {
    render(
      <Verdict
        testId="elimination-overlay"
        round={{ round: 2, votes, eliminated: { username: "Bilal", role: "undercover", user_id: "u4" } }}
        currentUserId="u1"
      />,
    )
    expect(screen.getByTestId("elimination-overlay")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "game.undercover.verdict.chose" })).toBeInTheDocument()
    expect(screen.getByText("games.undercover.roles.undercover")).toBeInTheDocument()
    expect(screen.getByText("Maryam and Idris")).toBeInTheDocument()
  })

  it('says "you" when the seat that emptied is yours, with your word', () => {
    render(
      <Verdict
        round={{ round: 2, votes, eliminated: { username: "Bilal", role: "civilian", user_id: "u4" } }}
        currentUserId="u4"
        myWord={{ arabic: "صبر", latin: "Sabr" }}
      />,
    )
    expect(screen.getByRole("heading", { name: "game.undercover.verdict.choseYou" })).toBeInTheDocument()
    expect(screen.getByText("صبر")).toBeInTheDocument()
  })

  it("without an elimination, only says the votes are in", () => {
    render(<Verdict round={{ round: 1, votes: [], eliminated: null }} />)
    expect(screen.getByRole("heading", { name: "game.undercover.verdict.noOne" })).toBeInTheDocument()
    expect(screen.queryByRole("group")).not.toBeInTheDocument()
  })
})

describe("Verdict: what Mr. White guessed, for the whole table", () => {
  const mrWhiteOut = { username: "Bilal", role: "mr_white", user_id: "u4" }

  it("says it on the round that voted him out (the table used to learn nothing)", () => {
    render(<Verdict round={{ round: 2, votes, eliminated: mrWhiteOut, mr_white_guess: { word: "Sabr", correct: false } }} currentUserId="u1" />)
    expect(screen.getByTestId("mr-white-guess")).toBeInTheDocument()
  })

  it("says nothing of a guess on a round without one", () => {
    render(<Verdict round={{ round: 1, votes, eliminated: { username: "Idris", role: "civilian", user_id: "u2" } }} currentUserId="u1" />)
    expect(screen.queryByTestId("mr-white-guess")).not.toBeInTheDocument()
  })
})
