import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { Alert } from "../alert"
import { initialsOf } from "../avatar"
import { Button } from "../button"
import { Field, Input } from "../field"

describe("Button", () => {
  it("defaults to type=button and ignores clicks while loading", () => {
    // Prepare
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Starting
      </Button>,
    )
    const button = screen.getByRole("button", { name: /Starting/ })

    // Act
    fireEvent.click(button)

    // Assert
    expect(button).toHaveAttribute("type", "button")
    expect(button).toHaveAttribute("aria-busy", "true")
    expect(onClick).not.toHaveBeenCalled()
  })

  it("renders its child when asChild", () => {
    render(
      <Button asChild variant="link">
        <a href="/rooms">Rooms</a>
      </Button>,
    )
    expect(screen.getByRole("link", { name: "Rooms" })).toHaveAttribute("data-slot", "button")
  })
})

describe("Field", () => {
  it("labels the control and links the error with role=alert", () => {
    render(
      <Field label="Room code" error="No open room with that code." errorTestId="form-error">
        <Input />
      </Field>,
    )

    const input = screen.getByLabelText("Room code")
    const error = screen.getByRole("alert")
    expect(input).toHaveAttribute("aria-invalid", "true")
    expect(input.getAttribute("aria-describedby")).toBe(error.id)
    expect(error).toHaveAttribute("data-testid", "form-error")
  })

  it("describes the control with the hint when there is no error", () => {
    render(
      <Field label="Display name" hint="Shown to everyone.">
        <Input />
      </Field>,
    )
    expect(screen.getByLabelText("Display name")).toHaveAccessibleDescription("Shown to everyone.")
  })
})

describe("Alert", () => {
  it("is an alert for errors and a status for information", () => {
    const { rerender } = render(<Alert data-testid="form-error">Invalid email or password.</Alert>)
    expect(screen.getByRole("alert")).toHaveAttribute("data-testid", "form-error")

    rerender(<Alert tone="info">Showing the last known state.</Alert>)
    expect(screen.getByRole("status")).toHaveTextContent("Showing the last known state.")
  })
})

describe("initialsOf", () => {
  it("takes two words, or two letters of one word, in any script", () => {
    expect(initialsOf("Maryam Idris")).toBe("MI")
    expect(initialsOf("bilal")).toBe("BI")
    expect(initialsOf("يوسف")).toBe("يو")
  })
})
