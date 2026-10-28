import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { GameRules } from "../GameRules"

describe("GameRules", () => {
  it("gives every game the anchor the home's 'How it plays' links point to", () => {
    // Prepare / Act
    const { container } = render(<GameRules />)

    // Assert: GamesFihrist links to /about#undercover, #codenames, #kalimat, #quiz
    for (const id of ["undercover", "codenames", "kalimat", "quiz"]) {
      const article = container.querySelector(`article#${id}`)
      expect(article, id).not.toBeNull()
      // a round in four numbered steps, named by its own heading
      expect(within(article as HTMLElement).getAllByRole("listitem")).toHaveLength(4)
      expect(article?.getAttribute("aria-labelledby")).toBe(`${id}-title`)
    }
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("rules.title")
  })
})
