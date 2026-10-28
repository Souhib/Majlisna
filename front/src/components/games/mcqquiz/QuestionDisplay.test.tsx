import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { QuestionDisplay } from "./QuestionDisplay"

describe("QuestionDisplay", () => {
  it("renders question in an h2 heading", () => {
    render(<QuestionDisplay question="Who built the Kaaba?" />)
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Who built the Kaaba?")
  })

  it("marks an Arabic question as Arabic, so it is set in Amiri", () => {
    render(<QuestionDisplay question="أيُّ مدينةٍ خُطِّطت على شكلِ دائرةٍ كاملة؟" />)
    const heading = screen.getByRole("heading", { level: 2 })
    expect(heading).toHaveAttribute("lang", "ar")
    expect(heading).toHaveAttribute("dir", "rtl")
  })
})
