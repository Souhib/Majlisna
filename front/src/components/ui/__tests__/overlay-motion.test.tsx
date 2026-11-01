import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Dialog, DialogContent, DialogDescription, DialogTitle, Sheet, SheetContent, SheetDescription, SheetTitle } from "../dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../dropdown-menu"
import { Popover, PopoverContent, PopoverTrigger } from "../popover"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../select"

/**
 * Overlays run on the motion grammar (WP-18, F8): they arrive on --ease-out and leave on
 * --ease-in at 0.66 × the arrival (the browser's `ease`, with exits as long as entries,
 * before). tw-animate's `animate-in`/`animate-out` read --tw-duration and --tw-ease, which
 * the `duration-*` and `ease-*` utilities set.
 */

const STATE_EXIT = "data-[state=closed]:duration-[calc(var(--dur-state)*0.66)]"
const MOVE_EXIT = "data-[state=closed]:duration-[calc(var(--dur-move)*0.66)]"

function classesOf(slot: string) {
  const el = document.querySelector(`[data-slot="${slot}"]`)
  if (!el) throw new Error(`no ${slot}`)
  return (el.getAttribute("class") ?? "").split(/\s+/)
}

function expectStateMotion(slot: string) {
  const classes = classesOf(slot)
  expect(classes).toContain("duration-(--dur-state)")
  expect(classes).toContain("ease-(--ease-out)")
  expect(classes).toContain("data-[state=closed]:ease-(--ease-in)")
  expect(classes).toContain(STATE_EXIT)
}

describe("overlay motion", () => {
  it("a dialog and its dim arrive on --ease-out and leave on --ease-in, faster", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Remove Maryam?</DialogTitle>
          <DialogDescription>She can join again with the code.</DialogDescription>
        </DialogContent>
      </Dialog>,
    )

    expectStateMotion("dialog-content")
    expectStateMotion("dialog-overlay")
  })

  it("a sheet lands on --ease-settle and leaves on --ease-in in 0.66 × its move", () => {
    render(
      <Sheet open>
        <SheetContent>
          <SheetTitle>Menu</SheetTitle>
          <SheetDescription>Pages</SheetDescription>
        </SheetContent>
      </Sheet>,
    )

    const classes = classesOf("sheet-content")
    expect(classes).toContain("duration-(--dur-move)")
    expect(classes).toContain("ease-(--ease-settle)")
    expect(classes).toContain("data-[state=closed]:ease-(--ease-in)")
    expect(classes).toContain(MOVE_EXIT)
  })

  it("a menu, a popover and a select do the same", () => {
    render(
      <>
        <DropdownMenu open>
          <DropdownMenuTrigger>Room</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>Copy the link</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Popover open>
          <PopoverTrigger>Meaning</PopoverTrigger>
          <PopoverContent>Patience</PopoverContent>
        </Popover>
        <Select open value="sa">
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="sa">Saudi Arabia</SelectItem>
          </SelectContent>
        </Select>
      </>,
    )

    expectStateMotion("dropdown-menu-content")
    expectStateMotion("popover-content")
    expectStateMotion("select-content")
  })
})

describe("toast motion (sonner, re-timed in brand.css)", () => {
  // vitest runs with `css: false`, so a `?raw` import of a stylesheet is empty: read the file.
  const css = readFileSync(resolve(process.cwd(), "src/styles/brand.css"), "utf8")

  function rule(selector: string) {
    const at = css.indexOf(`${selector} {`)
    if (at < 0) return null
    return css.slice(at + selector.length + 2, css.indexOf("}", at))
  }

  it("arrives on the tokens instead of sonner's 400 ms, and leaves on --ease-in at 0.66 ×", () => {
    const toast = rule("html [data-sonner-toast]") ?? ""
    expect(toast).toMatch(/transform var\(--dur-move\) var\(--ease-settle\)/)
    expect(toast).toMatch(/opacity var\(--dur-state\) var\(--ease-out\)/)
    expect(toast).toMatch(/height var\(--dur-move\) var\(--ease-settle\)/)

    const removed = rule('html [data-sonner-toast][data-removed="true"]') ?? ""
    expect(removed).toMatch(/transition-timing-function: var\(--ease-in\);/)
    expect(removed).toMatch(/calc\(var\(--dur-move\) \* 0\.66\)/)
  })
})
