import { fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { CodeTiles, CodeTilesInput } from "../CodeTiles"
import { Colophon } from "../Colophon"
import { Halqa } from "../Halqa"
import { Wordmark } from "../Wordmark"

function SingleInput({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial)
  return <CodeTilesInput id="room-code" label="Room code" length={5} value={value} onChange={setValue} />
}

function SplitInput() {
  const [value, setValue] = useState("")
  return (
    <CodeTilesInput
      split
      label="PIN"
      length={4}
      charset="digits"
      value={value}
      onChange={setValue}
      cellLabel={(i) => `Password digit ${i + 1}`}
    />
  )
}

describe("CodeTilesInput (single)", () => {
  it("keeps the given id and paints each character on its tile, upper-cased and filtered", () => {
    // Prepare
    const { container } = render(<SingleInput />)
    const input = container.querySelector("#room-code") as HTMLInputElement

    // Act
    fireEvent.change(input, { target: { value: "lu-l1m9" } })

    // Assert
    expect(input.value).toBe("LUL1M")
    const tiles = [...container.querySelectorAll(".code-tile")].map((t) => t.textContent)
    expect(tiles).toEqual(["L", "U", "L", "1", "M"])
    expect(screen.getByLabelText("Room code")).toBe(input)
  })
})

describe("CodeTilesInput (split)", () => {
  it("names each cell, advances on input and fills from a paste", () => {
    // Prepare
    render(<SplitInput />)
    const first = screen.getByLabelText("Password digit 1") as HTMLInputElement

    // Act
    fireEvent.change(first, { target: { value: "6" } })
    fireEvent.paste(screen.getByLabelText("Password digit 2"), { clipboardData: { getData: () => "9 8-1" } })

    // Assert
    const values = [1, 2, 3, 4].map((n) => (screen.getByLabelText(`Password digit ${n}`) as HTMLInputElement).value)
    expect(values).toEqual(["6", "9", "8", "1"])
  })

  it("ignores letters in a digits-only cell", () => {
    render(<SplitInput />)
    const first = screen.getByLabelText("Password digit 1") as HTMLInputElement

    fireEvent.change(first, { target: { value: "a" } })

    expect(first.value).toBe("")
  })
})

describe("CodeTiles (display)", () => {
  it("labels the group and stays left to right", () => {
    render(<CodeTiles label="Room code" value="LULIM" />)

    const group = screen.getByRole("group", { name: "Room code" })
    expect(group).toHaveClass("code-tiles")
    expect(group.querySelectorAll(".code-tile")).toHaveLength(5)
  })
})

describe("Halqa", () => {
  const seats = [
    { id: "a", name: "Yusuf", state: "host" as const },
    { id: "b", name: "Maryam", state: "in" as const },
    { id: "c", name: "Idris", state: "in" as const },
  ]

  it("draws open seats up to capacity and closes the ring at quorum", () => {
    const { container } = render(<Halqa seats={seats} capacity={8} quorum={3} dir="ltr" label="Three seated" />)

    expect(screen.getByRole("img", { name: "Three seated" })).toBeInTheDocument()
    expect(container.querySelectorAll("rect.s-open")).toHaveLength(5)
    expect(container.querySelector("circle.thread.closed")).not.toBeNull()
  })

  it("draws an open arc below quorum and hides itself without a label", () => {
    const { container } = render(<Halqa seats={seats.slice(0, 2)} capacity={8} quorum={3} dir="rtl" />)

    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(container.querySelector("circle.thread.closed")).toBeNull()
    // RTL fills anticlockwise: the arc sweeps with flag 0.
    expect(container.querySelector("path.thread")?.getAttribute("d")).toMatch(/A104 104 0 0 0 /)
  })
})

describe("Wordmark", () => {
  it("is one accessible image of the name, with the kashida woven from 80 px", () => {
    const { container, rerender } = render(<Wordmark size={32} />)
    expect(screen.getByRole("img", { name: "مجلسنا" })).toBeInTheDocument()
    expect(container.querySelector(".k")).toHaveClass("k-ink")

    rerender(<Wordmark size={120} />)
    expect(container.querySelector(".k")).not.toHaveClass("k-ink")
  })
})

describe("Colophon", () => {
  it("keeps an h2 title for the game-over hook and lists words, seals and actions", () => {
    render(
      <Colophon
        arch={false}
        title="Game Over"
        words={[{ word: "صبر", translit: "Ṣabr", meaning: "Patience" }]}
        seals={[{ title: "Taste of Victory", caption: "Maryam" }]}
        actions={<button type="button">Play again</button>}
      />,
    )

    expect(screen.getByRole("heading", { level: 2, name: "Game Over" })).toBeInTheDocument()
    expect(screen.getByText("صبر")).toHaveAttribute("lang", "ar")
    expect(screen.getByText("Taste of Victory")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Play again" })).toBeInTheDocument()
  })
})
